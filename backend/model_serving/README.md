# Model serving

Build this image once and run it with a different `MODEL_URI` for each model version. The initial app exposes a liveness route only; model loading and `/predict` are intentionally not stubbed with fake results.
