class NotFound(Exception):
    def __init__(self, kind: str, key: object):
        super().__init__(f"{kind} {key} not found")
        self.kind = kind
        self.key = key


class Conflict(Exception):
    pass


class InvalidUpload(Exception):
    pass
