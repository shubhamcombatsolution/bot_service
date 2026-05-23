class BaseTool:
    """
    Base class for all Tool.
    """
    def __init__(self, name, description):
        self.name = name
        self.description = description

    def process(self, *args, **kwargs):
        """
        Method to be overridden by child classes to handle specific tasks.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Any: Result of the processing.
        """
        raise NotImplementedError("The process method must be implemented by the subclass.")