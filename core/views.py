from django.http import Http404, JsonResponse
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db import models
from django.core.files.storage import default_storage
import random
import os
import uuid
import json

from .models import Card, Pack
from firebase_admin import auth as firebase_auth
from .firebase import (
	get_inventory,
	get_user_cards,
	get_user_coins,
	adjust_coins,
	add_cards,
	decrement_card,
	create_auction,
	list_active_auctions,
	list_user_auctions,
	place_bid,
	buy_now_purchase,
	cancel_auction,
	finalize_auction,
)

logger = logging.getLogger(__name__)
UserModel = get_user_model()


def is_admin_logged_in(request):
	return request.session.get('admin_logged_in', False)

POSITIONS_GROUPS = [
	{"label": "Goalkeeper", "options": [("GK", "Goalkeeper")]},
	{"label": "Defenders", "options": [
		("CB", "Center Back"),
		("LB", "Left Back"),
		("RB", "Right Back"),
		("LWB", "Left Wing Back"),
		("RWB", "Right Wing Back"),
		("SW", "Sweeper"),
	]},
	{"label": "Midfielders", "options": [
		("CDM", "Central Defensive Midfielder"),
		("CM", "Central Midfielder"),
		("CAM", "Central Attacking Midfielder"),
		("LM", "Left Midfielder"),
		("RM", "Right Midfielder"),
		("DM", "Defensive Midfielder"),
		("WM", "Wide Midfielder"),
	]},
	{"label": "Attackers/Forwards", "options": [
		("ST", "Striker"),
		("CF", "Center Forward"),
		("LW", "Left Winger"),
		("RW", "Right Winger"),
		("LF", "Left Forward"),
		("RF", "Right Forward"),
		("SS", "Supporting Striker"),
	]},
]

def list_view(request):
	logger.debug("list_view: admin_logged_in=%s method=%s", request.session.get('admin_logged_in'), request.method)
	if request.method == 'POST':
		if 'login' in request.POST:
			username = request.POST.get('username')
			password = request.POST.get('password')
			user = authenticate(request, username=username, password=password)
			if user and user.is_staff:
				request.session['admin_logged_in'] = True
				logger.info("Admin login via username successful: %s", username)
				return redirect('card_list')
			else:
				logger.warning("Admin login failed for username: %s", username)
				messages.error(request, 'Invalid credentials')
		elif 'logout' in request.POST:
			request.session.pop('admin_logged_in', None)
			logger.info("Admin logout via form")
			return redirect('card_list')

	admin_logged_in = is_admin_logged_in(request)

	try:
		page = int(request.GET.get("page", "1"))
		per_page = int(request.GET.get("per_page", "10"))
	except ValueError:
		page, per_page = 1, 10
	page = max(page, 1)
	per_page = max(min(per_page, 200), 1)

	qs = Card.objects.filter(is_deleted=False)

	league = (request.GET.get("league") or "").strip()
	club = (request.GET.get("club") or "").strip()
	position = (request.GET.get("position") or "").strip()
	search = (request.GET.get("search") or "").strip()

	if league:
		qs = qs.filter(league__icontains=league)
	if club:
		qs = qs.filter(club__icontains=club)
	if position:
		qs = qs.filter(position__icontains=position)
	if search:
		qs = qs.filter(name__icontains=search)

	sort = (request.GET.get("sort") or "overall_desc").strip().lower()

	if sort == "overall_desc":
		qs = qs.order_by('-rating')
	elif sort == "overall_asc":
		qs = qs.order_by('rating')
	else:
		qs = qs.order_by("external_id")

	paginator = Paginator(qs, per_page)
	page_obj = paginator.get_page(page)

	columns = ["Name", "Nation", "League", "Club", "Overall", "Position", "Revision"]

	context = {
		"cards": page_obj.object_list,
		"columns": columns,
		"page": page_obj.number,
		"per_page": per_page,
		"total": paginator.count,
		"pages": paginator.num_pages,
		"has_prev": page_obj.has_previous(),
		"has_next": page_obj.has_next(),
		"prev_page": page_obj.previous_page_number() if page_obj.has_previous() else None,
		"next_page": page_obj.next_page_number() if page_obj.has_next() else None,
		"csv_path": settings.PLAYER_DATA_CSV_PATH,
		"position_groups": POSITIONS_GROUPS,
		"selected": {
			"league": league,
			"club": club,
			"position": position,
			"sort": sort,
			"search": search,
		},
		"admin_logged_in": admin_logged_in,
	}
	return render(request, "core/list.html", context)


def google_login(request):
	if request.method != 'POST':
		logger.warning("google_login: invalid method %s", request.method)
		return JsonResponse({'error': 'Method not allowed'}, status=405)

	id_token = request.POST.get('id_token') or (request.headers.get('Authorization', '').replace('Bearer ', '') if request.headers.get('Authorization') else None)
	if not id_token:
		logger.warning("google_login: missing id_token; headers=%s", {k: request.headers.get(k) for k in ['Authorization']})
		return JsonResponse({'error': 'Missing id_token'}, status=400)

	try:
		decoded = firebase_auth.verify_id_token(id_token)
		logger.info("google_login: token verified; uid=%s email=%s", decoded.get('uid'), decoded.get('email'))
		# Extract basic profile info
		firebase_user = {
			'uid': decoded.get('uid'),
			'email': decoded.get('email'),
			'name': decoded.get('name'),
			'picture': decoded.get('picture'),
		}
		# Mark user logged in, but only set admin if allowed
		request.session['user_logged_in'] = True
		request.session['firebase_user'] = firebase_user
		admin_allowed = False
		email = firebase_user.get('email')
		try:
			if email and email in getattr(settings, 'ADMIN_EMAILS', []):
				admin_allowed = True
			elif email:
				user = UserModel.objects.filter(email__iexact=email).first()
				if user and (user.is_staff or user.is_superuser):
					admin_allowed = True
		except Exception:
			pass

		if admin_allowed:
			request.session['admin_logged_in'] = True
			logger.info("google_login: admin granted for email=%s", email)
		else:
			request.session.pop('admin_logged_in', None)
			logger.info("google_login: regular user login for email=%s", email)

		logger.debug("google_login: session set user_logged_in=True firebase_user=%s", {k: firebase_user.get(k) for k in ['uid','email','name']})
		return JsonResponse({'status': 'ok', 'user': firebase_user})
	except Exception as e:
		logger.exception("google_login: token verification failed: %s", e)
		return JsonResponse({'error': 'Invalid token', 'detail': str(e)}, status=401)


def google_logout(request):
	if request.method != 'POST':
		logger.warning("google_logout: invalid method %s", request.method)
		return JsonResponse({'error': 'Method not allowed'}, status=405)
	request.session.pop('admin_logged_in', None)
	request.session.pop('firebase_user', None)
	request.session.pop('user_logged_in', None)
	logger.info("google_logout: session cleared")
	return JsonResponse({'status': 'ok'})


def deleted_cards_view(request):
	if not is_admin_logged_in(request):
		return redirect('card_list')

	if request.method == 'POST':
		if 'restore' in request.POST:
			try:
				card_id = request.POST.get('card_id')
				card = Card.objects.get(id=card_id, is_deleted=True)
				card.is_deleted = False
				card.save()
				messages.success(request, f'Card {card.name} restored.')
			except Card.DoesNotExist:
				messages.error(request, 'Card not found.')
		elif 'permanent_delete' in request.POST:
			try:
				card_id = request.POST.get('card_id')
				card = Card.objects.get(id=card_id, is_deleted=True)

				try:
					pic = card.player_pic or ''
					if isinstance(pic, str):

						if pic.startswith(settings.MEDIA_URL):
							rel_path = pic[len(settings.MEDIA_URL):]
							file_path = os.path.join(str(settings.MEDIA_ROOT), rel_path)

							abs_media_root = os.path.abspath(str(settings.MEDIA_ROOT))
							abs_file_path = os.path.abspath(file_path)
							if abs_file_path.startswith(abs_media_root) and os.path.isfile(abs_file_path):
								os.remove(abs_file_path)
				except Exception:
					pass

				card.delete()
				messages.success(request, f'Card {card.name} permanently deleted.')
			except Card.DoesNotExist:
				messages.error(request, 'Card not found.')
		return redirect('deleted_cards')

	deleted_cards = Card.objects.filter(is_deleted=True).order_by('name')

	context = {
		'cards': deleted_cards,
		'columns': ["Name", "Nation", "League", "Club", "Overall", "Position"],
	}
	return render(request, "core/deleted_cards.html", context)


def create_card_view(request):
	if not is_admin_logged_in(request):
		return redirect('card_list')

	if request.method == 'POST':

		name = request.POST.get('name', '').strip()
		overall = request.POST.get('overall', '').strip()
		position = request.POST.get('position', '').strip()
		nation = request.POST.get('nation', '').strip()
		league = request.POST.get('league', '').strip()
		club = request.POST.get('club', '').strip()
		picture = request.POST.get('picture', '').strip()
		picture_file = request.FILES.get('picture_file')
		nation_pic = request.POST.get('nation_pic', '').strip()
		club_pic = request.POST.get('club_pic', '').strip()
		
		pace = request.POST.get('pace', '').strip()
		shooting = request.POST.get('shooting', '').strip()
		passing = request.POST.get('passing', '').strip()
		dribbling = request.POST.get('dribbling', '').strip()
		defending = request.POST.get('defending', '').strip()
		physical = request.POST.get('physical', '').strip()

		if not name or not overall or not position:
			messages.error(request, 'Name, Overall Rating, and Position are required.')
			return redirect('create_card')

		external_id = str(uuid.uuid4())[:8]

		if picture_file:
			ext = os.path.splitext(picture_file.name)[1].lower()
			filename = f"players/{uuid.uuid4().hex}{ext}"
			saved_path = default_storage.save(filename, picture_file)
			player_pic = f"{settings.MEDIA_URL}{saved_path}"
		else:
			player_pic = picture

		Card.objects.create(
			external_id=external_id,
			name=name,
			rating=int(overall) if overall.isdigit() else None,
			position=position,
			country=nation,
			league=league,
			club=club,
			nation_pic=nation_pic,
			club_pic=club_pic,
			player_pic=player_pic,
			pace=int(pace) if pace.isdigit() else None,
			shooting=int(shooting) if shooting.isdigit() else None,
			passing=int(passing) if passing.isdigit() else None,
			dribbling=int(dribbling) if dribbling.isdigit() else None,
			defending=int(defending) if defending.isdigit() else None,
			physical=int(physical) if physical.isdigit() else None,
		)

		messages.success(request, f'Card "{name}" created successfully with ID: {external_id}.')
		return redirect('card_list')

	return render(request, "core/create_card.html", {'initial_data': {}})


def edit_card_view(request, card_id):
	if not is_admin_logged_in(request):
		return redirect('card_list')

	try:
		card = Card.objects.get(id=card_id)
	except Card.DoesNotExist:
		raise Http404

	if request.method == 'POST':

		name = request.POST.get('name', '').strip()
		overall = request.POST.get('overall', '').strip()
		position = request.POST.get('position', '').strip()
		nation = request.POST.get('nation', '').strip()
		league = request.POST.get('league', '').strip()
		club = request.POST.get('club', '').strip()
		picture = request.POST.get('picture', '').strip()
		nation_pic = request.POST.get('nation_pic', '').strip()
		club_pic = request.POST.get('club_pic', '').strip()
		
		pace = request.POST.get('pace', '').strip()
		shooting = request.POST.get('shooting', '').strip()
		passing = request.POST.get('passing', '').strip()
		dribbling = request.POST.get('dribbling', '').strip()
		defending = request.POST.get('defending', '').strip()
		physical = request.POST.get('physical', '').strip()

		if not name or not overall or not position:
			messages.error(request, 'Name, Overall Rating, and Position are required.')
			return redirect('edit_card', card_id=card_id)

		picture_file = request.FILES.get('picture_file')
		if picture_file:
			ext = os.path.splitext(picture_file.name)[1].lower()
			filename = f"players/{uuid.uuid4().hex}{ext}"
			saved_path = default_storage.save(filename, picture_file)
			player_pic = f"{settings.MEDIA_URL}{saved_path}"
		else:
			player_pic = picture

		card.name = name
		card.rating = int(overall) if overall.isdigit() else None
		card.position = position
		card.country = nation
		card.league = league
		card.club = club
		card.nation_pic = nation_pic
		card.club_pic = club_pic
		card.player_pic = player_pic
		card.pace = int(pace) if pace.isdigit() else None
		card.shooting = int(shooting) if shooting.isdigit() else None
		card.passing = int(passing) if passing.isdigit() else None
		card.dribbling = int(dribbling) if dribbling.isdigit() else None
		card.defending = int(defending) if defending.isdigit() else None
		card.physical = int(physical) if physical.isdigit() else None
		card.save()

		messages.success(request, f'Card "{name}" updated successfully.')
		return redirect('card_list')

	initial_data = {
		'name': card.name or '',
		'overall': card.rating or '',
		'position': card.position or '',
		'nation': card.country or '',
		'league': card.league or '',
		'club': card.club or '',
		'picture': card.player_pic or '',
		'nation_pic': card.nation_pic or '',
		'club_pic': card.club_pic or '',
		'pace': card.pace or '',
		'shooting': card.shooting or '',
		'passing': card.passing or '',
		'dribbling': card.dribbling or '',
		'defending': card.defending or '',
		'physical': card.physical or '',
	}

	return render(request, "core/edit_card.html", {'card': card, 'initial_data': initial_data, 'form_action': request.path})


def delete_card(request, card_id):
	if not is_admin_logged_in(request):
		return redirect('card_list')
	
	try:
		card = Card.objects.get(id=card_id)
		if request.method == 'POST':
			if 'delete' in request.POST:
				card.is_deleted = True
				card.save()
				messages.success(request, f'Card {card.name} deleted.')
			elif 'restore' in request.POST:
				card.is_deleted = False
				card.save()
				messages.success(request, f'Card {card.name} restored.')
		return redirect('card_list')
	except Card.DoesNotExist:
		raise Http404


def detail_view(request, item_id: str):
	try:
		obj = Card.objects.get(external_id=str(item_id))
	except Card.DoesNotExist:
		raise Http404("Item not found")
	
	priority = ["Name", "Position", "Overall", "Club", "Country"]
	ordered = []
	seen = set()
	for key in priority:
		if key == "Name":
			value = obj.name
		elif key == "Position":
			value = obj.position
		elif key == "Overall":
			value = obj.rating
		elif key == "Club":
			value = obj.club
		elif key == "Country":
			value = obj.country
		else:
			continue
		if value is not None:
			ordered.append((key, value))
			seen.add(key)
	# Add other fields if needed, but for now, keep it simple

	context = {
		"card": obj,
		"id_col": "external_id",
		"csv_path": settings.PLAYER_DATA_CSV_PATH,
		"ordered_stats": ordered,
	}
	return render(request, "core/detail.html", context)


def collection_view(request):
	# Require login
	if not request.session.get('user_logged_in') or not request.session.get('firebase_user'):
		messages.error(request, 'Please log in to view your collection.')
		return redirect('card_list')

	uid = request.session['firebase_user'].get('uid')
	inv = get_inventory(uid)
	owned_cards = get_user_cards(uid)
	coins = int(inv.get('coins', 0))

	owned_card_ids = [card_id for card_id, qty in owned_cards.items() if qty > 0]
	cards_qs = Card.objects.filter(external_id__in=owned_card_ids, is_deleted=False)

	try:
		page = int(request.GET.get("page", "1"))
		per_page = int(request.GET.get("per_page", "10"))
	except ValueError:
		page, per_page = 1, 10
	page = max(page, 1)
	per_page = max(min(per_page, 200), 1)

	league = (request.GET.get("league") or "").strip()
	club = (request.GET.get("club") or "").strip()
	position = (request.GET.get("position") or "").strip()
	search = (request.GET.get("search") or "").strip()

	# Apply filters to queryset
	if league:
		cards_qs = cards_qs.filter(league__icontains=league)
	if club:
		cards_qs = cards_qs.filter(club__icontains=club)
	if position:
		cards_qs = cards_qs.filter(position__icontains=position)
	if search:
		cards_qs = cards_qs.filter(name__icontains=search)

	sort = (request.GET.get("sort") or "overall_desc").strip().lower()

	# Apply sorting to queryset
	if sort == "overall_desc":
		cards_qs = cards_qs.order_by('-rating')
	elif sort == "overall_asc":
		cards_qs = cards_qs.order_by('rating')
	else:
		cards_qs = cards_qs.order_by("external_id")

	# Paginate the queryset
	paginator = Paginator(cards_qs, per_page)
	page_obj = paginator.get_page(page)

	# Create cards list with quantities
	cards = [{'card': card, 'qty': owned_cards.get(card.external_id, 0)} for card in page_obj.object_list]

	context = {
		"cards": cards,
		"columns": ["Name", "Overall", "Position", "Club", "Nation", "Quantity", "Actions"],
		"coins": coins,
		"position_groups": POSITIONS_GROUPS,
		"page": page_obj.number,
		"per_page": per_page,
		"total": paginator.count,
		"pages": paginator.num_pages,
		"has_prev": page_obj.has_previous(),
		"has_next": page_obj.has_next(),
		"prev_page": page_obj.previous_page_number() if page_obj.has_previous() else None,
		"next_page": page_obj.next_page_number() if page_obj.has_next() else None,
		"page_obj": page_obj,
		"selected": {
			"league": league,
			"club": club,
			"position": position,
			"sort": sort,
			"search": search,
		},
	}
	return render(request, "core/collection.html", context)


def packs_view(request):
	# Require login
	if not request.session.get('user_logged_in') or not request.session.get('firebase_user'):
		messages.error(request, 'Please log in to open packs.')
		return redirect('card_list')

	if not Pack.objects.exists():
		Pack.objects.create(name='Bronze Pack', price=0, num_cards=5, chances={'0-59': 0.7, '60-79': 0.3})
		Pack.objects.create(name='Silver Pack', price=100, num_cards=5, chances={'60-79': 0.6, '80-89': 0.4})
		Pack.objects.create(name='Gold Pack', price=500, num_cards=5, chances={'70-89': 0.7, '90-100': 0.3})
	packs = Pack.objects.all()
	uid = request.session['firebase_user'].get('uid')
	coins = get_user_coins(uid)
	context = {
		"packs": packs,
		"coins": coins,
	}
	return render(request, "core/packs.html", context)


def open_pack(request, pack_id):
	# Require login
	if not request.session.get('user_logged_in') or not request.session.get('firebase_user'):
		messages.error(request, 'Please log in to open packs.')
		return redirect('card_list')

	pack = get_object_or_404(Pack, id=pack_id)
	uid = request.session['firebase_user'].get('uid')
	coins = get_user_coins(uid)
	if coins < pack.price:
		messages.error(request, "Not enough coins!")
		return redirect('packs')

	# Charge coins
	adjust_coins(uid, -int(pack.price))

	all_cards = list(Card.objects.filter(is_deleted=False))
	new_cards = []

	all_cards = list(Card.objects.filter(is_deleted=False))
	new_cards = []

	for _ in range(pack.num_cards):
		rand = random.random()
		cumulative = 0
		for range_str, prob in pack.chances.items():
			cumulative += prob
			if rand <= cumulative:
				min_r, max_r = map(int, range_str.split('-'))
				possible_cards = []
				for c in all_cards:
					if min_r <= c.get_rating() <= max_r:
						possible_cards.append(c)
				if possible_cards:
					chosen = random.choice(possible_cards)
					new_cards.append(chosen)
				break

	# Persist to Firestore: increment card quantities
	incs = {}
	for card in new_cards:
		incs[card.external_id] = incs.get(card.external_id, 0) + 1
	add_cards(uid, incs)
	coins = get_user_coins(uid)

	messages.success(request, f"Opened pack! Got {len(new_cards)} cards.")
	return render(request, "core/pack_result.html", {"new_cards": new_cards, "coins": coins})

def quicksell(request, card_id):
	# Require login
	if not request.session.get('user_logged_in') or not request.session.get('firebase_user'):
		messages.error(request, 'Please log in to quicksell players.')
		return redirect('card_list')

	uid = request.session['firebase_user'].get('uid')
	card = get_object_or_404(Card, external_id=card_id)
	price = card.quicksell_price()
	# Decrement one copy if available
	cards_after, ok = decrement_card(uid, card.external_id)
	if not ok:
		messages.error(request, "You don't own this card.")
		return redirect('collection')
	adjust_coins(uid, int(price))
	messages.success(request, f"Sold for {price} coins!")
	return redirect('collection')


# === Transfers / Auctions ===

def _require_login(request):
	if not request.session.get('user_logged_in') or not request.session.get('firebase_user'):
		messages.error(request, 'Please log in first.')
		return False
	return True


def transfers_view(request):
	if not _require_login(request):
		return redirect('card_list')
	# Opportunistically finalize expired auctions during listing
	uid = request.session['firebase_user'].get('uid')
	coins = get_user_coins(uid)
	auctions = list_active_auctions()
	# Hide user's own auctions from the public transfers page
	auctions = [a for a in auctions if str(a.get('seller_uid')) != str(uid)]

	# Pagination (6 per page)
	try:
		page = int(request.GET.get('page', '1'))
	except ValueError:
		page = 1
	paginator = Paginator(auctions, 6)
	page_obj = paginator.get_page(page)

	# Attach card objects for current page
	page_auctions = list(page_obj.object_list)
	card_ids = [str(a.get('card_id')) for a in page_auctions if a.get('card_id')]
	cards_map = {c.external_id: c for c in Card.objects.filter(external_id__in=card_ids, is_deleted=False)}
	for a in page_auctions:
		a['card'] = cards_map.get(str(a.get('card_id')))
	return render(request, 'core/transfers.html', {
		'auctions': page_auctions,
		'coins': coins,
		'page_obj': page_obj,
	})


def my_transfers_view(request):
	if not _require_login(request):
		return redirect('card_list')
	uid = request.session['firebase_user'].get('uid')
	coins = get_user_coins(uid)
	auctions = list_user_auctions(uid)
	# Also provide user's owned cards for creating new auctions
	owned_cards = get_user_cards(uid)
	owned_card_ids = [cid for cid, qty in owned_cards.items() if qty > 0]
	cards_qs = Card.objects.filter(external_id__in=owned_card_ids, is_deleted=False).order_by('name')

	# Pagination (6 per page)
	try:
		page = int(request.GET.get('page', '1'))
	except ValueError:
		page = 1
	paginator = Paginator(auctions, 6)
	page_obj = paginator.get_page(page)
	page_auctions = list(page_obj.object_list)
	card_ids = [str(a.get('card_id')) for a in page_auctions if a.get('card_id')]
	cards_map = {c.external_id: c for c in Card.objects.filter(external_id__in=card_ids, is_deleted=False)}
	for a in page_auctions:
		a['card'] = cards_map.get(str(a.get('card_id')))
	return render(request, 'core/my_transfers.html', {
		'auctions': page_auctions,
		'cards': cards_qs,
		'coins': coins,
		'page_obj': page_obj,
	})


def create_auction_view(request):
	if not _require_login(request):
		return redirect('card_list')
	if request.method != 'POST':
		return redirect('my_transfers')
	uid = request.session['firebase_user'].get('uid')
	card_id = (request.POST.get('card_id') or '').strip()
	start_price = int(request.POST.get('start_price') or '0')
	buy_now_price_raw = request.POST.get('buy_now_price')
	buy_now_price = int(buy_now_price_raw) if (buy_now_price_raw and buy_now_price_raw.isdigit()) else None
	duration_minutes = int(request.POST.get('duration_minutes') or '60')
	try:
		auction = create_auction(uid, card_id, start_price, buy_now_price, duration_minutes * 60)
		messages.success(request, 'Auction created.')
	except Exception as e:
		messages.error(request, f'Failed to create auction: {e}')
	return redirect('my_transfers')


def place_bid_view(request, auction_id: str):
	if not _require_login(request):
		return redirect('card_list')
	if request.method != 'POST':
		return redirect('transfers')
	uid = request.session['firebase_user'].get('uid')
	bid_amount = int(request.POST.get('bid_amount') or '0')
	try:
		place_bid(uid, auction_id, bid_amount)
		messages.success(request, 'Bid placed.')
	except Exception as e:
		messages.error(request, f'Failed to bid: {e}')
	return redirect('transfers')


def buy_now_view(request, auction_id: str):
	if not _require_login(request):
		return redirect('card_list')
	if request.method != 'POST':
		return redirect('transfers')
	uid = request.session['firebase_user'].get('uid')
	try:
		buy_now_purchase(uid, auction_id)
		messages.success(request, 'Purchased via Buy Now.')
	except Exception as e:
		messages.error(request, f'Failed to buy now: {e}')
	return redirect('transfers')


def cancel_auction_view(request, auction_id: str):
	if not _require_login(request):
		return redirect('card_list')
	if request.method != 'POST':
		return redirect('my_transfers')
	uid = request.session['firebase_user'].get('uid')
	try:
		cancel_auction(uid, auction_id)
		messages.success(request, 'Auction cancelled.')
	except Exception as e:
		messages.error(request, f'Failed to cancel: {e}')
	return redirect('my_transfers')
