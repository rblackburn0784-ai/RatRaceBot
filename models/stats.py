from dataclasses import dataclass, asdict

@dataclass(slots=True)
class DriverStats:
    nerve: int
    handling: int
    aggression: int
    mechanics: int
    reflexes: int
    showmanship: int

    def validate(self) -> None:
        vals = [self.nerve, self.handling, self.aggression, self.mechanics, self.reflexes, self.showmanship]
        for v in vals:
            if v < 1 or v > 8:
                raise ValueError("Each driver stat must be between 1 and 8.")
        if sum(vals) > 24:
            raise ValueError("Driver stat total must be 24 or less.")

    @property
    def total(self) -> int:
        return self.nerve + self.handling + self.aggression + self.mechanics + self.reflexes + self.showmanship

@dataclass(slots=True)
class CarStats:
    speed: int = 0
    acceleration: int = 0
    handling: int = 0
    durability: int = 0
    braking: int = 0
    heat: int = 0
    intimidation: int = 0
    reliability: int = 0
    pit_friendliness: int = 0

    def __add__(self, other: "CarStats") -> "CarStats":
        return CarStats(
            speed=self.speed + other.speed,
            acceleration=self.acceleration + other.acceleration,
            handling=self.handling + other.handling,
            durability=self.durability + other.durability,
            braking=self.braking + other.braking,
            heat=self.heat + other.heat,
            intimidation=self.intimidation + other.intimidation,
            reliability=self.reliability + other.reliability,
            pit_friendliness=self.pit_friendliness + other.pit_friendliness,
        )

    def as_dict(self) -> dict[str, int]:
        return asdict(self)
