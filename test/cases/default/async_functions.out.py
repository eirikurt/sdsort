async def main():
    result = await process_data()
    print(result)


# Processes the data
# ...in mysterious ways
async def process_data():
    data = await fetch_data()
    return data.upper()


# Fetches the data
async def fetch_data():
    return "data"
