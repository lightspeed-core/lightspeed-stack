"""Any exception that can occur when a user does not have enough tokens available."""

# pylint: disable=line-too-long


class QuotaExceedError(Exception):
    """Any exception that can occur when a user does not have enough tokens available."""

    def __init__(
        self, subject_id: str, subject_type: str, available: int, needed: int = 0
    ) -> None:
        """Construct exception object.

        Initialize the QuotaExceedError with the subject identity and token counts.

        Parameters:
                subject_id (str): Identifier of the subject (user id or cluster id).
            subject_type (str): Subject kind: "u" for user, "c" for cluster,
                                any other value treated as unknown.
                available (int): Number of tokens currently available to the subject.
                needed (int): Number of tokens required; defaults to 0.

        Attributes:
                subject_id (str): Copied from the `subject_id` parameter.
                available (int): Copied from the `available` parameter.
                needed (int): Copied from the `needed` parameter.
        """
        message: str = ""

        if needed == 0 and available <= 0:
            match subject_type:
                case "u":
                    message = f"User {subject_id} has no available tokens"
                case "c":
                    message = "Cluster has no available tokens"
                case _:
                    message = f"Unknown subject {subject_id} has no available tokens"
        else:
            match subject_type:
                case "u":
                    message = f"User {subject_id} has {available} tokens, but {needed} tokens are needed"  # noqa: E501
                case "c":
                    message = f"Cluster has {available} tokens, but {needed} tokens are needed"
                case _:
                    message = f"Unknown subject {subject_id} has {available} tokens, but {needed} tokens are needed"  # noqa: E501

        # call the base class constructor with the parameters it needs
        super().__init__(message)

        # custom attributes
        self.subject_id = subject_id
        self.available = available
        self.needed = needed
