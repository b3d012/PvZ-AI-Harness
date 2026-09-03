import pymem


class MemoryReader:
    """Thin read-only process-memory wrapper.

    ``process`` may be an executable name (the original API) or a PID.  PID
    attachment lets the runtime bind reader and window discovery to the same
    process without changing GameState v1 semantics.
    """

    def __init__(self, process: str | int):
        self.pm = pymem.Pymem(process)

    @property
    def process_id(self) -> int:
        return int(self.pm.process_id)

    def close(self) -> None:
        """Release the process handle; safe to call during runtime detach."""
        if getattr(self.pm, "process_handle", None):
            self.pm.close_process()

    def read_int(self, address: int) -> int:
        return self.pm.read_int(address)

    def read_uint(self, address: int) -> int:
        return self.pm.read_uint(address)

    def read_float(self, address: int) -> float:
        return self.pm.read_float(address)

    def read_byte(self, address: int) -> int:
        return self.pm.read_uchar(address)

    def read_bool(self, address: int) -> bool:
        return bool(self.pm.read_uchar(address))

    def read_pointer(self, address: int) -> int:
        # PvZ is a 32-bit process.
        return self.pm.read_uint(address)

    def resolve_pointer(self, base: int, offsets: list[int]) -> int:
        address = self.read_pointer(base)

        for offset in offsets[:-1]:
            address = self.read_pointer(address + offset)

        return address + offsets[-1]

    def read_int_chain(self, base: int, offsets: list[int]) -> int:
        address = self.resolve_pointer(base, offsets)
        return self.read_int(address)

    def read_uint_chain(self, base: int, offsets: list[int]) -> int:
        address = self.resolve_pointer(base, offsets)
        return self.read_uint(address)
