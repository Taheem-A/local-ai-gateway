class AIError(RuntimeError):
    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
