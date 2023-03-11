class GrocerorError(Exception):
    def __init__(self, entity: str, action: str, message: str) -> None:
        self.entity = entity
        self.action = action
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.entity.upper()} {self.action.upper()} {self.message}"
