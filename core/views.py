from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.core.paginator import Paginator
from django.contrib import messages
from django.db import models
import random
import os
import uuid

from .models import Card, UserCard, Pack, Profile


def get_profile():
	profile, created = Profile.objects.get_or_create(id=1)
	return profile

def is_admin_logged_in(request):
	return request.session.get('admin_logged_in', False)

# Hardcoded position groups for filter picker
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
			if username == os.getenv('ADMIN_USERNAME') and password == os.getenv('ADMIN_PASSWORD'):
				request.session['admin_logged_in'] = True
				return redirect('card_list')
			else:
				messages.error(request, 'Invalid credentials')
		elif 'logout' in request.POST:
			request.session.pop('admin_logged_in', None)
			return redirect('card_list')

	admin_logged_in = is_admin_logged_in(request)

	# Pagination
	try:
		page = int(request.GET.get("page", "1"))
		per_page = int(request.GET.get("per_page", "50"))
	except ValueError:
		page, per_page = 1, 50
	page = max(page, 1)
	per_page = max(min(per_page, 200), 1)

	qs = Card.objects.filter(is_deleted=False)

	# Filtering
	league = (request.GET.get("league") or "").strip()
	club = (request.GET.get("club") or "").strip()
	position = (request.GET.get("position") or "").strip()
	search = (request.GET.get("search") or "").strip()

	def contains_json_key_value(queryset, key, value):
		# Heuristic contains filter using string matching in JSON; portable across SQLite
		return queryset.filter(data__icontains=f'"{key}": "{value}"')

	if league:
		qs = contains_json_key_value(qs, "League", league)
	if club:
		qs = contains_json_key_value(qs, "Club", club)
	if position:
		qs = contains_json_key_value(qs, "Position", position)
	if search:
		# Search in both name field and JSON data Name field
		qs = qs.filter(
			models.Q(name__icontains=search) | 
			models.Q(data__icontains=f'"Name": "{search}"')
		)

	# Sorting
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

	# Fixed columns to show overall info + card type
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
		# Get form data
		name = request.POST.get('name', '').strip()
		overall = request.POST.get('overall', '').strip()
		position = request.POST.get('position', '').strip()
		nation = request.POST.get('nation', '').strip()
		league = request.POST.get('league', '').strip()
		club = request.POST.get('club', '').strip()
		picture = request.POST.get('picture', '').strip()
		nation_pic = request.POST.get('nation_pic', '').strip()
		club_pic = request.POST.get('club_pic', '').strip()
		
		# Stats
		pace = request.POST.get('pace', '').strip()
		shooting = request.POST.get('shooting', '').strip()
		passing = request.POST.get('passing', '').strip()
		dribbling = request.POST.get('dribbling', '').strip()
		defending = request.POST.get('defending', '').strip()
		physical = request.POST.get('physical', '').strip()

		if not name or not overall or not position:
			messages.error(request, 'Name, Overall Rating, and Position are required.')
			return redirect('create_card')

		# Generate unique external_id
		external_id = str(uuid.uuid4())[:8]

		# Create card data dict
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
		
		# Add stats
		if pace: data['Pace'] = pace
		if shooting: data['Shooting'] = shooting
		if passing: data['Passing'] = passing
		if dribbling: data['Dribbling'] = dribbling
		if defending: data['Defending'] = defending
		if physical: data['Physical'] = physical

		# Mark as admin created
		data['is_admin_created'] = True

		# Create the card
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
		# Get form data
		name = request.POST.get('name', '').strip()
		overall = request.POST.get('overall', '').strip()
		position = request.POST.get('position', '').strip()
		nation = request.POST.get('nation', '').strip()
		league = request.POST.get('league', '').strip()
		club = request.POST.get('club', '').strip()
		picture = request.POST.get('picture', '').strip()
		nation_pic = request.POST.get('nation_pic', '').strip()
		club_pic = request.POST.get('club_pic', '').strip()
		
		# Stats
		pace = request.POST.get('pace', '').strip()
		shooting = request.POST.get('shooting', '').strip()
		passing = request.POST.get('passing', '').strip()
		dribbling = request.POST.get('dribbling', '').strip()
		defending = request.POST.get('defending', '').strip()
		physical = request.POST.get('physical', '').strip()

		if not name or not overall or not position:
			messages.error(request, 'Name, Overall Rating, and Position are required.')
			return redirect('edit_card', card_id=card_id)

		# Update card data dict
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

		# Update the card
		card.name = name or None
		card.data = data
		card.save()

		messages.success(request, f'Card "{name}" updated successfully.')
		return redirect('card_list')

	# Pre-fill form with existing data
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
	# Prioritize common fields for nicer presentation, then show the rest sorted
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
	profile = get_profile()
	user_cards = UserCard.objects.filter(profile=profile).select_related('card')

	# Pagination
	try:
		page = int(request.GET.get("page", "1"))
		per_page = int(request.GET.get("per_page", "50"))
	except ValueError:
		page, per_page = 1, 50
	page = max(page, 1)
	per_page = max(min(per_page, 200), 1)

	# Filtering
	league = (request.GET.get("league") or "").strip()
	club = (request.GET.get("club") or "").strip()
	position = (request.GET.get("position") or "").strip()
	search = (request.GET.get("search") or "").strip()

	def contains_json_key_value(queryset, key, value):
		# Heuristic contains filter using string matching in JSON; portable across SQLite
		return queryset.filter(card__data__icontains=f'"{key}": "{value}"')

	if league:
		user_cards = contains_json_key_value(user_cards, "League", league)
	if club:
		user_cards = contains_json_key_value(user_cards, "Club", club)
	if position:
		user_cards = contains_json_key_value(user_cards, "Position", position)
	if search:
		# Search in both name field and JSON data Name field
		user_cards = user_cards.filter(
			models.Q(card__name__icontains=search) | 
			models.Q(card__data__icontains=f'"Name": "{search}"')
		)

	# Sorting
	sort = (request.GET.get("sort") or "overall_desc").strip().lower()

	def overall_value(card: Card):
		d = card.data or {}
		v = d.get("Overall") or d.get("Rating") or "0"
		try:
			return int(str(v))
		except Exception:
			return 0

	if sort in ("overall_desc", "overall_asc"):
		user_cards = sorted(user_cards, key=lambda uc: overall_value(uc.card), reverse=(sort == "overall_desc"))
	else:
		user_cards = user_cards.order_by("card__external_id")

	paginator = Paginator(user_cards, per_page)
	page_obj = paginator.get_page(page)

	cards = [uc.card for uc in page_obj.object_list]
	context = {
		"cards": cards,
		"columns": ["Name", "Overall", "Position", "Club", "Nation", "Actions"],
		"profile": profile,
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
    profile = get_profile()
    context = {
        "packs": packs,
        "profile": profile,
    }
    return render(request, "core/packs.html", context)


def open_pack(request, pack_id):
	pack = get_object_or_404(Pack, id=pack_id)
	profile = get_profile()

	if profile.coins < pack.price:
		messages.error(request, "Not enough coins!")
		return redirect('packs')

	profile.coins -= pack.price
	profile.save()

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
					
					user_card, created = UserCard.objects.get_or_create(profile=profile, card=chosen)
					if not created:
						user_card.quantity += 1
						user_card.save()
				break

	messages.success(request, f"Opened pack! Got {len(new_cards)} cards.")
	return render(request, "core/pack_result.html", {"new_cards": new_cards})


def quicksell(request, card_id):
	profile = get_profile()
	user_card = get_object_or_404(UserCard, profile=profile, card_id=card_id)
	price = user_card.card.quicksell_price()
	profile.coins += price
	profile.save()
	user_card.delete()
	messages.success(request, f"Sold for {price} coins!")
	return redirect('collection')
