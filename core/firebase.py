import os
import json
import logging
from typing import Dict, Tuple, Any

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
