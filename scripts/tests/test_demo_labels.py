import json

import httpx

from scripts import demo_common


def test_demo_submits_dataset_label_even_when_model_is_wrong():
    submitted = []

    def handle(request):
        submitted.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"request_id": "example", "prediction": 0})

    row = {"features": [1.0] * 13, "ground_truth_label": 2}
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        demo_common.send(client, row)
    assert submitted[-1] == (
        "/api/v1/feedback",
        {"prediction_id": "example", "ground_truth_label": 2},
    )


def test_demo_does_not_label_failed_inference():
    paths = []

    def handle(request):
        paths.append(request.url.path)
        return httpx.Response(503, json={"request_id": "failed", "prediction": None})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        code, _ = demo_common.send(
            client, {"features": [1.0] * 13, "ground_truth_label": 1}
        )
    assert code == 503 and paths == ["/api/v1/predict"]
