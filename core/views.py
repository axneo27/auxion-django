from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.core.paginator import Paginator
from django.contrib import messages
from django.db import models
from django.core.files.storage import default_storage
import random
import os
import uuid
import json

from .models import Card, Pack


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
	if request.method == 'POST':
		if 'login' in request.POST:
			username = request.POST.get('username')
			password = request.POST.get('password')
			expected_username = os.environ.get('ADMIN_USERNAME', 'admin')
			expected_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
			if username == expected_username and password == expected_password:
				request.session['admin_logged_in'] = True
				return redirect('card_list')
			else:
				messages.error(request, 'Invalid credentials')
		elif 'logout' in request.POST:
			request.session.pop('admin_logged_in', None)
			return redirect('card_list')

	admin_logged_in = is_admin_logged_in(request)

	try:
		page = int(request.GET.get("page", "1"))
		per_page = int(request.GET.get("per_page", "50"))
	except ValueError:
		page, per_page = 1, 50
	page = max(page, 1)
	per_page = max(min(per_page, 200), 1)

	qs = Card.objects.filter(is_deleted=False)

	league = (request.GET.get("league") or "").strip()
	club = (request.GET.get("club") or "").strip()
	position = (request.GET.get("position") or "").strip()
	search = (request.GET.get("search") or "").strip()

	def contains_json_key_value(queryset, key, value):

		return queryset.filter(data__icontains=f'"{key}": "{value}"')

	if league:
		qs = contains_json_key_value(qs, "League", league)
	if club:
		qs = contains_json_key_value(qs, "Club", club)
	if position:
		qs = contains_json_key_value(qs, "Position", position)
	if search:
		qs = qs.filter(
			models.Q(name__icontains=search) | 
			models.Q(data__icontains=f'"Name": "{search}"')
		)

	sort = (request.GET.get("sort") or "overall_desc").strip().lower()

	def overall_value(card: Card):
		d = card.data or {}
		v = d.get("Overall") or d.get("Rating") or "0"
		try:
			return int(str(v))
		except Exception:
			return 0

	if sort in ("overall_desc", "overall_asc"):
		qs = sorted(qs, key=overall_value, reverse=(sort == "overall_desc"))
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
					data = card.data or {}
					pic = data.get('Picture') or ''
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

		data = {}
		if name: data['Name'] = name
		if overall: data['Overall'] = overall
		if position: data['Position'] = position
		if nation: data['Nation'] = nation
		if league: data['League'] = league
		if club: data['Club'] = club
		if picture: data['Picture'] = picture
		if nation_pic: data['NationPic'] = nation_pic
		if club_pic: data['ClubPic'] = club_pic
		
		if pace: data['Pace'] = pace
		if shooting: data['Shooting'] = shooting
		if passing: data['Passing'] = passing
		if dribbling: data['Dribbling'] = dribbling
		if defending: data['Defending'] = defending
		if physical: data['Physical'] = physical

		if picture_file:
			ext = os.path.splitext(picture_file.name)[1].lower()
			filename = f"players/{uuid.uuid4().hex}{ext}"
			saved_path = default_storage.save(filename, picture_file)
			data['Picture'] = f"{settings.MEDIA_URL}{saved_path}"

		data['is_admin_created'] = True

		Card.objects.create(
			external_id=external_id,
			name=name or None,
			data=data
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

		data = card.data or {}
		data.update({
			'Name': name,
			'Overall': overall,
			'Position': position,
			'Nation': nation,
			'League': league,
			'Club': club,
			'Picture': picture,
			'NationPic': nation_pic,
			'ClubPic': club_pic,
			'Pace': pace,
			'Shooting': shooting,
			'Passing': passing,
			'Dribbling': dribbling,
			'Defending': defending,
			'Physical': physical,
		})

		picture_file = request.FILES.get('picture_file')
		if picture_file:
			ext = os.path.splitext(picture_file.name)[1].lower()
			filename = f"players/{uuid.uuid4().hex}{ext}"
			saved_path = default_storage.save(filename, picture_file)
			data['Picture'] = f"{settings.MEDIA_URL}{saved_path}"

		card.name = name or None
		card.data = data
		card.save()

		messages.success(request, f'Card "{name}" updated successfully.')
		return redirect('card_list')

	initial_data = {
		'name': card.name or card.data.get('Name', ''),
		'overall': card.data.get('Overall', ''),
		'position': card.data.get('Position', ''),
		'nation': card.data.get('Nation', ''),
		'league': card.data.get('League', ''),
		'club': card.data.get('Club', ''),
		'picture': card.data.get('Picture', ''),
		'nation_pic': card.data.get('NationPic', ''),
		'club_pic': card.data.get('ClubPic', ''),
		'pace': card.data.get('Pace', ''),
		'shooting': card.data.get('Shooting', ''),
		'passing': card.data.get('Passing', ''),
		'dribbling': card.data.get('Dribbling', ''),
		'defending': card.data.get('Defending', ''),
		'physical': card.data.get('Physical', ''),
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
	
	priority = ["Name", "Position", "Overall", "Club", "Nation"]
	data = obj.data or {}
	ordered = []
	seen = set()
	for key in priority:
		if key in data:
			ordered.append((key, data[key]))
			seen.add(key)
	for key in sorted(k for k in data.keys() if k not in seen):
		ordered.append((key, data[key]))

	context = {
		"card": obj,
		"id_col": "external_id",
		"csv_path": settings.PLAYER_DATA_CSV_PATH,
		"ordered_stats": ordered,
	}
	return render(request, "core/detail.html", context)


def collection_view(request):
	owned_cards_str = request.GET.get('owned_cards', '{}')
	try:
		owned_cards = json.loads(owned_cards_str)
	except json.JSONDecodeError:
		owned_cards = {}
	
	# Update session with owned_cards
	request.session['owned_cards'] = json.dumps(owned_cards)
	
	# owned_cards is dict {card_id: quantity}
	owned_cards_list = []
	for card_id, qty in owned_cards.items():
		if qty > 0:
			try:
				card = Card.objects.get(external_id=card_id)
				owned_cards_list.append({'card': card, 'qty': qty})
			except Card.DoesNotExist:
				pass
	user_cards = owned_cards_list

	try:
		coins = int(request.GET.get('coins', '0'))
	except ValueError:
		coins = 0

	try:
		page = int(request.GET.get("page", "1"))
		per_page = int(request.GET.get("per_page", "50"))
	except ValueError:
		page, per_page = 1, 50
	page = max(page, 1)
	per_page = max(min(per_page, 200), 1)

	league = (request.GET.get("league") or "").strip()
	club = (request.GET.get("club") or "").strip()
	position = (request.GET.get("position") or "").strip()
	search = (request.GET.get("search") or "").strip()

	def contains_json_key_value(items, key, value):
		return [item for item in items if f'"{key}": "{value}"' in json.dumps(item['card'].data)]

	if league:
		user_cards = contains_json_key_value(user_cards, "League", league)
	if club:
		user_cards = contains_json_key_value(user_cards, "Club", club)
	if position:
		user_cards = contains_json_key_value(user_cards, "Position", position)
	if search:
		user_cards = [item for item in user_cards if search.lower() in (item['card'].name or '').lower() or f'"Name": "{search}"' in json.dumps(item['card'].data)]

	sort = (request.GET.get("sort") or "overall_desc").strip().lower()

	def overall_value(item):
		d = item['card'].data or {}
		v = d.get("Overall") or d.get("Rating") or "0"
		try:
			return int(str(v))
		except Exception:
			return 0

	if sort in ("overall_desc", "overall_asc"):
		user_cards = sorted(user_cards, key=overall_value, reverse=(sort == "overall_desc"))
	else:
		user_cards = sorted(user_cards, key=lambda item: item['card'].external_id)

	paginator = Paginator(user_cards, per_page)
	page_obj = paginator.get_page(page)

	cards = page_obj.object_list
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
    if not Pack.objects.exists():
        Pack.objects.create(name='Bronze Pack', price=0, num_cards=5, chances={'0-59': 0.7, '60-79': 0.3})
        Pack.objects.create(name='Silver Pack', price=100, num_cards=5, chances={'60-79': 0.6, '80-89': 0.4})
        Pack.objects.create(name='Gold Pack', price=500, num_cards=5, chances={'70-89': 0.7, '90-100': 0.3})
    packs = Pack.objects.all()
    try:
        coins = int(request.GET.get('coins', '0'))
    except ValueError:
        coins = 0
    context = {
        "packs": packs,
        "coins": coins,
    }
    return render(request, "core/packs.html", context)


def open_pack(request, pack_id):
	pack = get_object_or_404(Pack, id=pack_id)
	try:
		coins = int(request.GET.get('coins', '0'))
	except ValueError:
		coins = 0

	if coins < pack.price:
		messages.error(request, "Not enough coins!")
		return redirect('packs')

	coins -= pack.price

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

	# Update session with new cards
	owned_cards_data = request.session.get('owned_cards', '{}')
	if isinstance(owned_cards_data, dict):
		owned_cards = owned_cards_data
		request.session['owned_cards'] = json.dumps(owned_cards)
	else:
		try:
			owned_cards = json.loads(owned_cards_data)
		except json.JSONDecodeError:
			owned_cards = {}
	
	for card in new_cards:
		external_id = card.external_id
		if external_id in owned_cards:
			owned_cards[external_id] += 1
		else:
			owned_cards[external_id] = 1
	
	request.session['owned_cards'] = json.dumps(owned_cards)

	messages.success(request, f"Opened pack! Got {len(new_cards)} cards.")
	return render(request, "core/pack_result.html", {"new_cards": new_cards, "coins": coins})


def quicksell(request, card_id):
	try:
		coins = int(request.GET.get('coins', '0'))
	except ValueError:
		coins = 0
	card = get_object_or_404(Card, external_id=card_id)
	price = card.quicksell_price()
	coins += price
	messages.success(request, f"Sold for {price} coins!")
	return redirect('collection')
