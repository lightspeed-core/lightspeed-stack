# if-elif chain, can be refactored using pattern matching
if isinstance(event, TaskStatusUpdateEvent):
    if event.status.state == TaskState.failed:
        self._task_state = TaskState.failed
        self._task_status_message = event.status.message
    elif (
        event.status.state == TaskState.auth_required
        and self._task_state != TaskState.failed
    ):
        self._task_state = TaskState.auth_required
        self._task_status_message = event.status.message
    elif (
        event.status.state == TaskState.input_required
        and self._task_state not in (TaskState.failed, TaskState.auth_required)
    ):
        self._task_state = TaskState.input_required
        self._task_status_message = event.status.message
    elif self._task_state == TaskState.working:
        # Keep tracking the working message/status
        self._task_status_message = event.status.message
