class COOPSameOriginAllowPopupsMiddleware:
    """
    Sets Cross-Origin-Opener-Policy to same-origin-allow-popups.
    This helps Firebase's popup window avoid being closed by COOP restrictions.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        return response
