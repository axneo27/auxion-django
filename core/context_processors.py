from .firebase import get_user_cards

def get_collection_count(request):
    """Return total owned card count from Firestore for logged-in user."""
    firebase_user = request.session.get('firebase_user')
    if not request.session.get('user_logged_in') or not firebase_user:
        return 0
    uid = firebase_user.get('uid')
    owned_cards = get_user_cards(uid)
    return sum(qty for qty in owned_cards.values() if qty > 0)

def collection_count(request):
    return {'collection_count': get_collection_count(request)}