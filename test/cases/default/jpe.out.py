from dataclasses import dataclass


class JointPositionErrorConfig(TaskConfig):
    starting_offset_x: int = 0
    starting_offset_y: int = 0


@dataclass(frozen=True)
class JPEScoring(Scoring):
    three_plane_error: ScoreCategory


@dataclass(frozen=True)
class JPETask(XYZTask[JPEScoring, JointPositionErrorConfig]):
    @staticmethod
    def _get_config_class():
        return JointPositionErrorConfig

    @staticmethod
    def get_axis_range(task_config: JointPositionErrorConfig) -> int:
        # Increase the range if needed to account for the starting offset
        max_offset = max(abs(task_config.starting_offset_x), abs(task_config.starting_offset_y))
        multiplier = 2 + max_offset // 20
        return multiplier * 32
