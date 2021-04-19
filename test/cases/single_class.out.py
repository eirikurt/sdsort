class Salsa:
    def __init__(self):
        pass

    def party(self):
        self.open()
        self.dip()
        self.close()

    def open(self):
        print("open")

    @classmethod
    def dip(cls):
        print("dip")

    @staticmethod
    def close():
        print("close")
