# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# SPDX-License-Identifier: CC-BY-NC-4.0

# @yaml
# signature: submit_subtask '<index>' '<answer>'
# docstring: records a solved Cybench subtask checkpoint without terminating the session. Use the 1-based subtask index and the exact answer string.
# arguments:
#   index:
#     type: integer
#     description: 1-based subtask index from the prompt.
#     required: true
#   answer:
#     type: string
#     description: exact answer for the solved subtask.
#     required: true
submit_subtask() {
    if [ $# -lt 2 ]; then
        echo "Usage: submit_subtask <index> <answer>"
        return
    fi

    local subtask_index="$1"
    shift

    echo -n "<<SUBTASK||"
    echo -n "$subtask_index"
    echo -n "||"
    echo -n "$@"
    echo "||SUBTASK>>"
}
