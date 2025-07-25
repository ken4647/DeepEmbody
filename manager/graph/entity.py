from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid
from .primitive_spec import PRIMITIVE_SPECS  # 导入标准原语规范


class EntityType(Enum):
    GENERIC = "generic"
    CONTROLLABLE = "controllable"
    COMPUTING = "computing"
    SYSTEM = "system"
    HUMAN = "human"
    ROOM = "room"


class RelationType(Enum):
    # ROOM RELATIONS
    # these are used to construct the main structure of the tree
    # while other relations are used to provide auxiliary information (graph)
    PARENT_OF = "parent_of"
    CHILD_OF = "child_of"


@dataclass
class EntityMetadata:
    name: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)


class Entity:

    def __init__(
        self,
        entity_id: str,
        entity_type: EntityType,
        entity_name: str,
        metadata: Optional[EntityMetadata] = None,
    ):

        self.entity_id = entity_id
        self.entity_type = entity_type
        self.entity_name = entity_name
        self.metadata = metadata or EntityMetadata()

        self.relations: Dict[str, List["Entity"]] = {
            rel_type.value: [] for rel_type in RelationType
        }

        self.primitives: List[str] = []
        self.primitive_bindings: Dict[str, callable] = {}  # 绑定的原语函数

        self.is_active = True
        self.created_at = None
        self.updated_at = None

    def add_primitive(self, primitive: str) -> None:
        if primitive not in self.primitives:
            self.primitives.append(primitive)

    def remove_primitive(self, primitive: str) -> None:
        if primitive in self.primitives:
            self.primitives.remove(primitive)

    def has_primitive(self, primitive: str) -> bool:
        return primitive in self.primitives

    def add_relation(
        self, relation_type: RelationType, target_entity: "Entity"
    ) -> None:
        if target_entity not in self.relations[relation_type.value]:
            self.relations[relation_type.value].append(target_entity)

    def remove_relation(
        self, relation_type: RelationType, target_entity: "Entity"
    ) -> None:
        if target_entity in self.relations[relation_type.value]:
            self.relations[relation_type.value].remove(target_entity)

    def get_relations(self, relation_type: RelationType) -> List["Entity"]:
        return self.relations[relation_type.value].copy()

    def add_parent(self, parent_entity: "Entity") -> None:
        if parent_entity == self:
            raise ValueError("Entity cannot be its own parent")
        self.add_relation(RelationType.PARENT_OF, parent_entity)
        parent_entity.add_relation(RelationType.CHILD_OF, self)

    def add_child(self, child_entity: "Entity") -> None:
        if child_entity == self:
            raise ValueError("Entity cannot be its own child")
        self.add_relation(RelationType.CHILD_OF, child_entity)
        child_entity.add_relation(RelationType.PARENT_OF, self)

    def remove_parent(self, parent_entity: "Entity") -> None:
        self.remove_relation(RelationType.PARENT_OF, parent_entity)
        parent_entity.remove_relation(RelationType.CHILD_OF, self)

    def remove_child(self, child_entity: "Entity") -> None:
        self.remove_relation(RelationType.CHILD_OF, child_entity)
        child_entity.remove_relation(RelationType.PARENT_OF, self)

    def get_parent(self) -> List["Entity"]:
        parent = self.get_relations(RelationType.PARENT_OF)
        if len(parent) > 1:
            raise ValueError("Entity has multiple parents")
        return parent[0] if parent else None

    def get_children(self) -> List["Entity"]:
        return self.get_relations(RelationType.CHILD_OF)

    def is_root(self) -> bool:
        return self.get_parent() is None

    def get_absolute_path(self) -> str:
        path = self.entity_name
        parent = self.get_parent()
        if parent:
            if parent.is_root():
                path = f"/{path}"
            else:
                path = f"{parent.get_absolute_path()}/{path}"
        return path

    def get_entity_by_path(self, path: str) -> Optional["Entity"]:
        """
        Find and return the entity at the given path relative to this entity.
        Path is a string of entity names separated by '/', e.g. 'room1/book1'.
        Returns the target Entity if found, otherwise None.
        """
        # Remove leading/trailing slashes and split
        path_split = [p for p in path.strip("/").split("/") if p]
        if not path_split:
            return self  # path is empty or just '/', return self

        current = self
        for name in path_split:
            children = current.get_children()
            found = False
            for child in children:
                if child.entity_name == name:
                    current = child
                    found = True
                    break
            if not found:
                return None  # Path does not exist
        return current

    def bind_primitive(self, primitive_name: str, func: callable) -> None:
        """
        Bind a function to a primitive name for this entity.
        """
        if primitive_name not in PRIMITIVE_SPECS:
            raise ValueError(
                f"Primitive '{primitive_name}' is not a standard primitive.")
        self.primitive_bindings[primitive_name] = func
        self.add_primitive(primitive_name)

    def _check_primitive_args(self, primitive_name: str, kwargs: dict):
        """
        Check if the arguments match the primitive spec.
        """
        spec = PRIMITIVE_SPECS[primitive_name]
        expected_args = spec["args"]
        if set(kwargs.keys()) != set(expected_args):
            raise ValueError(
                f"Arguments for '{primitive_name}' must be {expected_args}, got {list(kwargs.keys())}")

    def _check_primitive_returns(self, primitive_name: str, result: dict):
        """
        Check if the return value matches the primitive spec.
        """
        spec = PRIMITIVE_SPECS[primitive_name]
        expected_returns = spec["returns"]
        if set(result.keys()) != set(expected_returns.keys()):
            raise ValueError(
                f"Return value for '{primitive_name}' must have keys {list(expected_returns.keys())}, got {list(result.keys())}")
        for k, v in expected_returns.items():
            if not isinstance(result[k], v):
                raise TypeError(
                    f"Return value for '{primitive_name}' key '{k}' must be {v}, got {type(result[k])}")

    def __getattr__(self, name):
        if name in self.primitive_bindings:
            def wrapper(**kwargs):
                self._check_primitive_args(name, kwargs)
                result = self.primitive_bindings[name](**kwargs)
                self._check_primitive_returns(name, result)
                return result
            return wrapper
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}', or this primitive is not bound, available primitives: {self.primitives}")


class Room(Entity):

    def __init__(
        self,
        room_id: str,
        room_name: str,
        metadata: Optional[EntityMetadata] = None,
    ):
        super().__init__(
            entity_id=room_id,
            entity_type=EntityType.ROOM,
            entity_name=room_name,
            metadata=metadata,
        )

        self.capacity: Optional[int] = None
        self.room_type: str = "generic"  # special attributes for Room
        self.is_accessible: bool = True


def create_generic_entity(entity_name: str, **kwargs) -> Entity:
    return Entity(uuid.uuid4(), EntityType.GENERIC, entity_name, **kwargs)


def create_controllable_entity(entity_name: str, **kwargs) -> Entity:
    return Entity(uuid.uuid4(), EntityType.CONTROLLABLE, entity_name, **kwargs)


def create_computing_entity(entity_name: str, **kwargs) -> Entity:
    return Entity(uuid.uuid4(), EntityType.COMPUTING, entity_name, **kwargs)


def create_human_entity(entity_name: str, **kwargs) -> Entity:
    return Entity(uuid.uuid4(), EntityType.HUMAN, entity_name, **kwargs)


def create_room_entity(room_name: str, room_type: str = "generic", **kwargs) -> Room:
    room = Room(uuid.uuid4(), room_name, **kwargs)
    room.room_type = room_type
    return room


def create_root_room() -> Room:
    return create_room_entity("/")
