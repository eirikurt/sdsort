class Program(ArchivableEntity, frozen=True):
    __table_name__ = "program"

    id: UUID = PrimaryKey(default_factory=uuid4)
    organization_id: UUID
    patient_id: UUID
    clinic_id: UUID
    created_by_user_id: UUID
    name: str
    instructions: str
    activities: list[ProgramActivity]
    status: ProgramStatus


class ProgramPatch(BaseModel):
    organization_id: UUID | None = None
    patient_id: UUID | None = None
    clinic_id: UUID | None = None
    created_by_user_id: UUID | None = None
    name: str | None = None
    instructions: str | None = None
    activities: list[ProgramActivity] | None = None
    status: ProgramStatus | None = None
    is_archived: bool | None = None


class ProgramRepo(Repo[Program, ProgramPatch]):
    @overload
    async def demand(self, *, id: UUID, patient_ids: Sequence[UUID]) -> Program: ...
    @overload
    async def demand(self, **kwargs: Unpack[ProgramFilter]) -> Program: ...
    async def demand(self, **kwargs):
        if "patient_ids" in kwargs:
            kwargs["patient_id"] = kwargs.pop("patient_ids")
        return await self._demand(**kwargs)

    async def get(self, **kwargs: Unpack[ProgramFilter]):
        return await self._get(**kwargs)

    @overload
    async def get_many(self, **kwargs: Unpack[ProgramsFilter]) -> PaginatedList[Program]: ...
    @overload
    async def get_many(
        self, identifiers: Sequence[ProgramFilter | ProgramsFilter]
    ) -> PaginatedList[Program]: ...
    async def get_many(self, *args, **kwargs):
        return await self._get_many(*args, **kwargs)

    async def archive(self, program: Program):
        return await self.patch(program, ProgramPatch(is_archived=True))
