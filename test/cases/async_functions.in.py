async def fetch_data():
    return "data"


async def process_data():
    data = await fetch_data()
    return data.upper()


async def main():
    result = await process_data()
    print(result)
