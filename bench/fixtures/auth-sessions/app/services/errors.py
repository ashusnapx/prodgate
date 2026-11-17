class NotAuthenticated(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class RateLimited(Exception):
    pass


class InviteExpired(Exception):
    pass


class PasswordPolicyError(Exception):
    pass


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass
