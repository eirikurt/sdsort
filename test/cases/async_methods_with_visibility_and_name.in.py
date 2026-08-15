class AsyncService:
    def public_result(self):
        pass

    async def public_z(self):
        await self.public_value()

    def _protected_b(self):
        pass

    async def public_value(self):
        return self.public_result()

    def __private_a(self):
        pass

    async def public_a(self):
        await self.public_z()

    async def __dunder_b__(self):
        pass

    async def _protected_a(self):
        pass

    def __dunder_a__(self):
        pass
