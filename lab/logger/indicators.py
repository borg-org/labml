from collections import deque
from typing import Dict

import numpy as np

try:
    import torch
except ImportError:
    torch = None


def _to_numpy(value):
    type_ = type(value)

    if type_ == float or type_ == int:
        return value

    if type_ == np.ndarray:
        return value

    if torch is not None:
        if type_ == torch.nn.parameter.Parameter:
            return value.data.cpu().numpy()
        if type_ == torch.Tensor:
            return value.data.cpu().numpy()

    assert False, f"Unknown type {type_}"


class Indicator:
    def __init__(self, *, name: str, is_print: bool):
        self.is_print = is_print
        self.name = name

    def clear(self):
        pass

    def is_empty(self) -> bool:
        raise NotImplementedError()

    def to_dict(self) -> Dict:
        return dict(name=self.name,
                    class_name=self.__class__.__name__)

    def collect_value(self, value):
        raise NotImplementedError()

    def get_mean(self) -> float:
        raise NotImplementedError()

    def get_histogram(self):
        raise NotImplementedError()

    @property
    def mean_key(self):
        return f'{self.name}'


class Queue(Indicator):
    def __init__(self, name: str, queue_size=10, is_print=False):
        super().__init__(name=name, is_print=is_print)
        self._values = deque(maxlen=queue_size)

    def collect_value(self, value):
        self._values.append(_to_numpy(value))

    def to_dict(self) -> Dict:
        res = super().to_dict().copy()
        res.update({'queue_size': self._values.maxlen})
        return res

    def is_empty(self) -> bool:
        return len(self._values) == 0

    def get_mean(self) -> float:
        return float(np.mean(self._values))

    def get_histogram(self):
        return self._values

    @property
    def mean_key(self):
        return f'{self.name}.mean'


class _Collection(Indicator):
    def __init__(self, name: str, is_print=False):
        super().__init__(name=name, is_print=is_print)
        self._values = []

    def collect_value(self, value):
        self._values.append(_to_numpy(value))

    def clear(self):
        self._values = []

    def is_empty(self) -> bool:
        return len(self._values) == 0

    def get_mean(self) -> float:
        return float(np.mean(self._values))

    def get_histogram(self):
        return self._values


class Histogram(_Collection):
    @property
    def mean_key(self):
        return f'{self.name}.mean'


class Scalar(_Collection):
    def get_histogram(self):
        return None


class Indexed(Indicator):
    def __init__(self, name: str):
        super().__init__(name=name, is_print=False)
        self._values = []

    def clear(self):
        self._values = []

    def collect_value(self, value):
        if type(value) == tuple:
            assert len(value) == 2
            self._values.append(value)
        else:
            assert type(value) == list
            self._values += value

    def is_empty(self) -> bool:
        return len(self._values) == 0

    def get_mean(self) -> float:
        raise None

    def get_histogram(self):
        return None
