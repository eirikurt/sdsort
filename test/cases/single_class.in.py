class Salsa:
    def __init__(self):
        pass

    @classmethod
    def dip(cls):
        print("dip")

    @staticmethod
    def close():
        print("close")

    def open(self):
        print("open")

    def party(self):
        self.open()
        self.dip()
        self.close()
