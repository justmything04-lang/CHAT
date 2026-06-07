from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class BaseStore(ABC):
    @abstractmethod
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def upsert_user(self, user_id: int, updates: Dict[str, Any]) -> None: ...

    @abstractmethod
    def get_all_users(self) -> Dict[str, Dict[str, Any]]: ...

    @abstractmethod
    def delete_user(self, user_id: int) -> None: ...
