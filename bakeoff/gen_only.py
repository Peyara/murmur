#!/usr/bin/env python3
"""Just generate worlds without audits to measure speed."""
import time
from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
from bakeoff.worldgen.sandbox import generate_balanced_batch

start = time.time()
print("Generating 5 test worlds...")

batch = generate_balanced_batch(
    config=DEFAULT_WORLD_CONFIG,
    total_seeds=5,
    target_campaigns_per_flavor=1.0,
    dev_fraction=0.3,
    verbose=False,
)

elapsed = time.time() - start
worlds_per_sec = len(batch["worlds"]) / elapsed

print(f"✓ Generated {len(batch['worlds'])} worlds in {elapsed:.1f}s")
print(f"  Rate: {worlds_per_sec:.2f} worlds/sec")
print(f"  Estimated time for 100 worlds: {100/worlds_per_sec:.0f}s ({100/worlds_per_sec/60:.0f} min)")
print(f"\nCampaigns per flavor: {batch['campaigns_per_flavor']}")
print(f"Total campaigns: {sum(batch['campaigns_per_flavor'].values())}")
