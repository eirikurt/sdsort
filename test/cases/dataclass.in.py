from dataclasses import dataclass


@dataclass
class SomeDataClass:
    id: int
    name: str

    def salute(self):
        return f"Hi Miss {self.name}"

    def __repr__(self):
        return self.salute()
