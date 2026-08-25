import pymem


class MemoryReader:
    def __init__(self, process_name: str):
        self.pm = pymem.Pymem(process_name)

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