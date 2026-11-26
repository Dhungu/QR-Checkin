class DomainError(Exception):
    status_code = 400
    code = "ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(DomainError):
    status_code = 409
    code = "CONFLICT"


class BadRequest(DomainError):
    status_code = 422
    code = "BAD_REQUEST"
