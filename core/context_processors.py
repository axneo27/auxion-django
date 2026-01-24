import json

def get_collection_count(request):
    owned_cards_data = request.session.get('owned_cards', '{}')
    if isinstance(owned_cards_data, dict):
        owned_cards = owned_cards_data
        # Normalize to string
        request.session['owned_cards'] = json.dumps(owned_cards)
    else:
        try:
            owned_cards = json.loads(owned_cards_data)
        except json.JSONDecodeError:
            owned_cards = {}
    
    return sum(qty for qty in owned_cards.values() if qty > 0)

def collection_count(request):
    return {'collection_count': get_collection_count(request)}