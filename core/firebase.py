import os
import json
import logging
from typing import Dict, Tuple, Any, List, Optional
from datetime import datetime, timedelta, timezone

from django.conf import settings

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK once per process, and log status
if not firebase_admin._apps:
    service_account_path = os.path.join(str(settings.BASE_DIR), 'auxiondjango-firebase-adminsdk-fbsvc-a335700f6a.json')
    env_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
    try:
        if env_json:
            logger.info("Firebase Admin: initializing from FIREBASE_SERVICE_ACCOUNT_JSON env var%s",
                        " (prod)" if not getattr(settings, 'DEBUG', False) else "")
            try:
                data = json.loads(env_json)
                cred = credentials.Certificate(data)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase Admin initialized via env JSON object")
            except Exception as e_obj:
                logger.warning("Env JSON credential init failed (%s); attempting temp file path", e_obj)
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.json') as tmp:
                        tmp.write(env_json)
                        tmp_path = tmp.name
                    cred = credentials.Certificate(tmp_path)
                    firebase_admin.initialize_app(cred)
                    logger.info("Firebase Admin initialized via env JSON temp file")
                except Exception as e_tmp:
                    logger.exception("Firebase Admin env init via temp file failed: %s", e_tmp)
                    raise
        elif os.path.isfile(service_account_path):
            logger.info("Firebase Admin: using service account file at %s", service_account_path)
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized via file")
        else:
            logger.warning("Firebase Admin: no env JSON and service account file not found; attempting default init")
            firebase_admin.initialize_app()
            logger.info("Firebase Admin initialized via default app config")
    except Exception as e:
        logger.exception("Firebase Admin initialization failed: %s", e)
else:
    logger.debug("Firebase Admin already initialized, skipping")


def _client():
    """Return Firestore client."""
    return firestore.client()


def _inv_doc(uid: str):
    return _client().collection('inventories').document(uid)


def _auctions_col():
    return _client().collection('auctions')


def ensure_inventory(uid: str) -> Dict:
    """Ensure user inventory doc exists; return its data.

    Structure: { coins: int, cards: { external_id: qty:int } }
    """
    doc_ref = _inv_doc(uid)
    snap: Any = doc_ref.get()
    exists = False
    try:
        exists = bool(snap.exists)
    except Exception:
        try:
            exists = bool(snap.exists())
        except Exception:
            exists = False
    if not exists:
        data = { 'coins': 0, 'cards': {} }
        doc_ref.set(data)
        logger.info("Created new inventory for uid=%s", uid)
        return data
    try:
        data = snap.to_dict() or {}
    except Exception:
        data = {}
    data.setdefault('coins', 0)
    data.setdefault('cards', {})
    return data


def get_inventory(uid: str) -> Dict:
    return ensure_inventory(uid)


def get_user_coins(uid: str) -> int:
    return int(get_inventory(uid).get('coins', 0))


def get_user_cards(uid: str) -> Dict[str, int]:
    cards = get_inventory(uid).get('cards') or {}
    # Normalize quantities to int
    return {str(k): int(v) for k, v in cards.items()}


def adjust_coins(uid: str, delta: int) -> int:
    """Adjust coin balance by delta; return new balance."""
    doc_ref = _inv_doc(uid)
    inv = ensure_inventory(uid)
    new_val = max(0, int(inv.get('coins', 0)) + int(delta))
    doc_ref.set({'coins': new_val}, merge=True)
    logger.debug("adjust_coins: uid=%s delta=%s new=%s", uid, delta, new_val)
    return new_val


def add_cards(uid: str, card_ids: Dict[str, int]) -> Dict[str, int]:
    """Increment quantities for given external_id -> qty increments; return new cards map."""
    inv = ensure_inventory(uid)
    cards = inv.get('cards') or {}
    for cid, inc in card_ids.items():
        if inc <= 0:
            continue
        cards[cid] = int(cards.get(cid, 0)) + int(inc)
    _inv_doc(uid).set({'cards': cards}, merge=True)
    logger.debug("add_cards: uid=%s changes=%s", uid, card_ids)
    return {str(k): int(v) for k, v in cards.items()}


def decrement_card(uid: str, card_id: str) -> Tuple[Dict[str, int], bool]:
    """Decrement quantity of a card by 1 if available and remove key at 0.

    Returns (new_cards_map, success_flag).
    """
    inv = ensure_inventory(uid)
    cards = inv.get('cards') or {}
    qty = int(cards.get(card_id, 0))
    if qty <= 0:
        return ({str(k): int(v) for k, v in cards.items()}, False)
    # compute new map and persist by replacing 'cards' field
    new_qty = qty - 1
    if new_qty > 0:
        cards[card_id] = new_qty
    else:
        cards.pop(card_id, None)
    _inv_doc(uid).update({'cards': cards})
    logger.debug("decrement_card: uid=%s card_id=%s new_qty=%s", uid, card_id, new_qty)
    return ({str(k): int(v) for k, v in cards.items()}, True)


# === Auctions helpers ===

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_auction(
    seller_uid: str,
    card_id: str,
    start_price: int,
    buy_now_price: Optional[int],
    duration_seconds: int,
) -> Dict:
    """Create a new auction document and decrement seller's card quantity."""
    # Ensure seller owns the card
    cards_after, ok = decrement_card(seller_uid, card_id)
    if not ok:
        raise ValueError("Seller does not own the card to auction")

    start_time = _now_iso()
    end_time = (datetime.now(timezone.utc) + timedelta(seconds=int(duration_seconds))).isoformat()
    auction_doc = {
        'card_id': str(card_id),
        'seller_uid': str(seller_uid),
        'start_price': int(start_price),
        'buy_now_price': int(buy_now_price) if buy_now_price is not None else None,
        'start_time': start_time,
        'end_time': end_time,
        'current_bid': None,
        'current_bidder_uid': None,
        'status': 'active',
        'created_at': _now_iso(),
    }
    ref = _auctions_col().document()
    ref.set(auction_doc)
    auction_doc['id'] = ref.id
    logger.info("create_auction: id=%s card=%s seller=%s", ref.id, card_id, seller_uid)
    return auction_doc


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _is_expired(auction: Dict) -> bool:
    try:
        end_ts = auction.get('end_time') or ""
        return bool(end_ts) and (datetime.now(timezone.utc) >= _parse_iso(str(end_ts)))
    except Exception:
        return False


def list_active_auctions() -> List[Dict]:
    snaps = _auctions_col().where('status', '==', 'active').stream()
    auctions: List[Dict] = []
    for s in snaps:
        d = s.to_dict() or {}
        d['id'] = s.id
        auctions.append(d)
    # Opportunistic expiration handling
    for a in auctions:
        if _is_expired(a):
            try:
                finalize_auction(a['id'])
            except Exception:
                logger.exception("list_active_auctions: finalize failed for %s", a['id'])
    # Re-query to return up-to-date active list
    snaps = _auctions_col().where('status', '==', 'active').stream()
    auctions = []
    for s in snaps:
        d = s.to_dict() or {}
        d['id'] = s.id
        auctions.append(d)
    return auctions


def list_user_auctions(seller_uid: str) -> List[Dict]:
    snaps = _auctions_col().where('seller_uid', '==', str(seller_uid)).stream()
    auctions: List[Dict] = []
    for s in snaps:
        d = s.to_dict() or {}
        d['id'] = s.id
        auctions.append(d)
    # Opportunistic expiration
    for a in auctions:
        if a.get('status') == 'active' and _is_expired(a):
            try:
                finalize_auction(a['id'])
            except Exception:
                logger.exception("list_user_auctions: finalize failed for %s", a['id'])
    return auctions


def get_auction(auction_id: str) -> Optional[Dict]:
    snap: Any = _auctions_col().document(auction_id).get()
    try:
        exists = bool(getattr(snap, 'exists', False))
    except Exception:
        exists = False
    if not exists:
        return None
    try:
        d = snap.to_dict() or {}
    except Exception:
        d = {}
    d['id'] = auction_id
    return d


def place_bid(bidder_uid: str, auction_id: str, bid_amount: int) -> Dict:
    """Place a bid, validates timing and price; does not transfer coins yet."""
    a = get_auction(auction_id)
    if not a or a.get('status') != 'active':
        raise ValueError("Auction not active")
    if _is_expired(a):
        finalize_auction(auction_id)
        raise ValueError("Auction expired")

    # Prevent bidding on own auction
    if str(a.get('seller_uid')) == str(bidder_uid):
        raise PermissionError("Cannot bid on your own auction")
    start_price = int(a.get('start_price') or 0)
    current_bid = int(a.get('current_bid') or 0)
    buy_now = a.get('buy_now_price')
    bid_amount = int(bid_amount)
    # Validate bid
    min_required = max(start_price, current_bid + 1) if current_bid else start_price
    if bid_amount < min_required:
        raise ValueError("Bid too low")
    # Optional: if bid meets/exceeds buy-now, treat as buy-now
    if buy_now is not None and bid_amount >= int(buy_now):
        return buy_now_purchase(bidder_uid, auction_id)
    # Ensure bidder has enough coins
    if get_user_coins(bidder_uid) < bid_amount:
        raise ValueError("Insufficient coins for bid")
    # Update auction with bid
    _auctions_col().document(auction_id).update({
        'current_bid': bid_amount,
        'current_bidder_uid': str(bidder_uid),
    })
    logger.info("place_bid: auction=%s bidder=%s amount=%s", auction_id, bidder_uid, bid_amount)
    return get_auction(auction_id) or {}


def buy_now_purchase(bidder_uid: str, auction_id: str) -> Dict:
    a = get_auction(auction_id)
    if not a or a.get('status') != 'active':
        raise ValueError("Auction not active")
    # Prevent buying own auction
    if str(a.get('seller_uid')) == str(bidder_uid):
        raise PermissionError("Cannot buy your own auction")
    buy_now = a.get('buy_now_price')
    if buy_now is None:
        raise ValueError("Buy-now not available")
    amount = int(buy_now)
    # Check coins
    if get_user_coins(bidder_uid) < amount:
        raise ValueError("Insufficient coins")
    # Transfer card to bidder, move coins seller<-bidder, and close
    seller_uid = str(a.get('seller_uid'))
    card_id = str(a.get('card_id'))
    add_cards(bidder_uid, {card_id: 1})
    adjust_coins(bidder_uid, -amount)
    adjust_coins(seller_uid, amount)
    _auctions_col().document(auction_id).delete()
    logger.info("buy_now: auction=%s buyer=%s amount=%s", auction_id, bidder_uid, amount)
    return {'status': 'ok', 'transferred_to': bidder_uid, 'amount': amount}


def finalize_auction(auction_id: str) -> Dict:
    """Finalize auction at expiry: award to highest bidder or return to seller."""
    a = get_auction(auction_id)
    if not a:
        return {'status': 'not_found'}
    if a.get('status') != 'active':
        return {'status': 'not_active'}

    # If not expired yet, do nothing
    if not _is_expired(a):
        return {'status': 'not_expired'}

    seller_uid = str(a.get('seller_uid'))
    card_id = str(a.get('card_id'))
    current_bid = a.get('current_bid')
    current_bidder_uid = a.get('current_bidder_uid')

    if current_bid and current_bidder_uid:
        amount = int(current_bid)
        # Award to bidder if they still have enough coins; else treat as no-bid
        if get_user_coins(str(current_bidder_uid)) >= amount:
            add_cards(str(current_bidder_uid), {card_id: 1})
            adjust_coins(str(current_bidder_uid), -amount)
            adjust_coins(seller_uid, amount)
            _auctions_col().document(auction_id).delete()
            logger.info("finalize: auction=%s winner=%s amount=%s", auction_id, current_bidder_uid, amount)
            return {'status': 'awarded', 'winner': str(current_bidder_uid), 'amount': amount}

    # No valid bid; return card to seller and delete auction
    add_cards(seller_uid, {card_id: 1})
    _auctions_col().document(auction_id).delete()
    logger.info("finalize: auction=%s returned to seller=%s", auction_id, seller_uid)
    return {'status': 'returned'}


def cancel_auction(seller_uid: str, auction_id: str) -> Dict:
    """Seller cancels auction early; return the card to seller if active."""
    a = get_auction(auction_id)
    if not a:
        return {'status': 'not_found'}
    if a.get('seller_uid') != seller_uid:
        raise PermissionError("Not your auction")
    if a.get('status') != 'active':
        return {'status': 'not_active'}
    # Return card to seller and delete auction
    add_cards(seller_uid, {str(a.get('card_id')): 1})
    _auctions_col().document(auction_id).delete()
    logger.info("cancel: auction=%s seller=%s", auction_id, seller_uid)
    return {'status': 'cancelled'}
