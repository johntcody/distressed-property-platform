"""MAO calculation logic."""


class MAOCalculator:
    DEFAULT_PROFIT_MARGIN = 0.70  # 70% rule

    def calculate(self, arv: float, rehab_cost: float, profit_margin: float = None) -> float:
        """MAO = (ARV * margin) - rehab_cost."""
        margin = profit_margin or self.DEFAULT_PROFIT_MARGIN
        # TODO: support custom margin per deal strategy (wholesale vs fix-and-flip)
        return (arv * margin) - rehab_cost
