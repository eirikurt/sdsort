class Program(ArchivableEntity, frozen=True):
    pass


class ProgramPatch(BaseModel):
    pass


class ProgramRepo(Repo[Program, ProgramPatch]):
    async def archive(self, program: Program):
        return await self.patch(program, ProgramPatch(is_archived=True))
