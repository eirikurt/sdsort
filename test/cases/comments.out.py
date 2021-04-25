# Here is a comment
from typing import Optional


class Comment:
    SOME_CONSTANT = 1234
    ANOTHER_CONSTANT = "asdf"

    async def splu(
        self,
        lots,
        and_lots,
        of_arguments,
        in_this_method,
        so_multiple,
        lines,
        perhaps,
        pretty,
        please,
        mr,
        black,
    ):
        """This method serves no purpose
        It's fake"""
        await self.send_below(
            lots,
            and_lots,
            of_arguments,
            in_this_method,
            so_multiple,
            len(lines),
            sum([perhaps, pretty, please, mr, black]),
        )
        here = (
            "is a long string that will span multiple lines asælk jasdlfkj asdfk asdælfkj asdlfkj asdlfkj asdflkj "
            "asdflk j look"
        )

    async def send_below(
        self,
        parameter1,
        parameter2,
        parameter3: str,
        parameter4: int,
        parameter5: float,
        parameter6: Optional[int] = None,
    ):
        print("I was called")
        # Stuff got printed
