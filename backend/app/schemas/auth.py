from pydantic import BaseModel


class LogoutRead(BaseModel):
    logout_url: str
