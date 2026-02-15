# Fetches the data
async def fetch_data():
    return "data"


# Processes the data
# ...in mysterious ways
async def process_data():
    data = await fetch_data()
    return data.upper()


async def main():
    result = await process_data()
    print(result)
