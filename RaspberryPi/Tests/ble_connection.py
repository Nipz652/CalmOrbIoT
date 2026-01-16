#!/usr/bin/env python3
import asyncio
from dbus_next.aio import MessageBus
from dbus_next import Variant, BusType

SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab"
CHAR_UUID = "abcd1234-5678-90ab-cdef-1234567890ab"

value_store = bytearray(b"Hello Pi")

class ToyCharacteristic:
    def __init__(self, path):
        self.path = path
        self.flags = ["read", "write"]
        self.UUID = CHAR_UUID

    async def ReadValue(self, options):
        print("📥 READ:", value_store)
        return [Variant('y', b) for b in value_store]

    async def WriteValue(self, value, options):
        global value_store
        value_store = bytearray([v.value for v in value])
        print("📤 WRITE:", value_store.decode())


class ToyService:
    def __init__(self, path):
        self.path = path
        self.UUID = SERVICE_UUID
        self.primary = True
        self.characteristic = ToyCharacteristic(path + "/char1")


async def main():
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    service = ToyService("/com/pitoy/service0")

    print("🔵 BLE GATT server started as PiToyBase")
    print("➡️ Advertising Service UUID:", SERVICE_UUID)

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
