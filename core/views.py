from django.http import Http404
from django.shortcuts import render
from django.conf import settings
from django.core.paginator import Paginator

from .models import Card

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
	# Pagination
	try:
		page = int(request.GET.get("page", "1"))
		per_page = int(request.GET.get("per_page", "50"))
	except ValueError:
		page, per_page = 1, 50
	page = max(page, 1)
	per_page = max(min(per_page, 200), 1)

	qs = Card.objects.all()

	# Filtering
	league = (request.GET.get("league") or "").strip()
	club = (request.GET.get("club") or "").strip()
	position = (request.GET.get("position") or "").strip()

	def contains_json_key_value(queryset, key, value):
		# Heuristic contains filter using string matching in JSON; portable across SQLite
		return queryset.filter(data__icontains=f'"{key}": "{value}"')

	if league:
		qs = contains_json_key_value(qs, "League", league)
	if club:
		qs = contains_json_key_value(qs, "Club", club)
	if position:
		qs = contains_json_key_value(qs, "Position", position)

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
		},
	}
	return render(request, "core/list.html", context)


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
