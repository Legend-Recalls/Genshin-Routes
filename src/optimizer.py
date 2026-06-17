"""Viterbi-based offline route trajectory optimization engine."""

import json
import logging
import time
from pathlib import Path
import numpy as np

from .constants import (
    LOST_EMISSION_COST, LOST_TRANSITION_PENALTY, MAX_SPEED_TILES_PER_SEC,
    DEFAULT_TILE_SIZE, TRANSITION_SPEED_MULTIPLIER, TELEPORT_TRANSITION_COST,
    OVER_SPEED_BASE_PENALTY, OVER_SPEED_VELOCITY_MULTIPLIER, TELEPORT_DISTANCE_PX,
)

logger = logging.getLogger(__name__)


class RouteOptimizer:
    def __init__(
        self,
        lost_emission_cost: float = LOST_EMISSION_COST,
        lost_transition_penalty: float = LOST_TRANSITION_PENALTY,
        max_speed_tiles_per_sec: float = MAX_SPEED_TILES_PER_SEC,
    ):
        self.lost_emission_cost = lost_emission_cost
        self.lost_transition_penalty = lost_transition_penalty
        self.max_speed = max_speed_tiles_per_sec

        if lost_emission_cost < 0:
            raise ValueError(f"lost_emission_cost must be non-negative, got {lost_emission_cost}")
        if lost_transition_penalty < 0:
            raise ValueError(f"lost_transition_penalty must be non-negative, got {lost_transition_penalty}")
        if max_speed_tiles_per_sec <= 0:
            raise ValueError(f"max_speed_tiles_per_sec must be positive, got {max_speed_tiles_per_sec}")

    def _calc_transition_cost(self, state_a: dict, state_b: dict) -> float:
        """Calculate transition cost between two states based on travel velocity."""
        tile_a = state_a.get("tile")
        tile_b = state_b.get("tile")

        # Handle dummy lost states
        if tile_a is None and tile_b is None:
            return 0.0
        if tile_a is None or tile_b is None:
            return self.lost_transition_penalty

        # Both are valid tiles
        map_x_a, map_y_a = state_a.get("map_x"), state_a.get("map_y")
        map_x_b, map_y_b = state_b.get("map_x"), state_b.get("map_y")

        if map_x_a is None or map_y_a is None or map_x_b is None or map_y_b is None:
            # Fall back to tile coordinate distance (converted to approximate pixels)
            dist = float(np.sqrt((tile_b[0] - tile_a[0]) ** 2 + (tile_b[1] - tile_a[1]) ** 2)) * DEFAULT_TILE_SIZE
        else:
            # Compute pixel distance
            dx = map_x_b - map_x_a
            dy = map_y_b - map_y_a
            dist = float(np.sqrt(dx ** 2 + dy ** 2))

        # Time difference
        dt = state_b.get("timestamp", 0.0) - state_a.get("timestamp", 0.0)
        
        # dist is in pixels. tile_size is 256.
        # So velocity in tiles per second = (dist / tile_size) / dt
        if dt <= 0.0:
            return 0.0
        velocity = (dist / DEFAULT_TILE_SIZE) / dt

        if velocity == 0.0:
            return 0.0
        elif velocity <= self.max_speed:
            return TRANSITION_SPEED_MULTIPLIER * velocity
        else:
            if state_b.get("event_type") == "teleport":
                # Allow large jump because the localizer marked it as a teleport
                return TELEPORT_TRANSITION_COST
            # Heavy penalty for teleportation / large jumps
            return OVER_SPEED_BASE_PENALTY + OVER_SPEED_VELOCITY_MULTIPLIER * velocity

    def optimize_route(self, route_dir: Path) -> Path:
        """Run Viterbi pass over route candidates and write optimized_route.json."""
        route_path = route_dir / "route.json"
        if not route_path.exists():
            raise FileNotFoundError(f"route.json not found in {route_dir}")

        with open(route_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        if not entries:
            logger.warning("No entries in route.json to optimize.")
            return route_path

        logger.info(f"Optimizing trajectory for {len(entries)} frames in {route_dir.name}...")
        start_time = time.perf_counter()

        # Step 1: Build state sequences for each frame
        # Each state is a dict: {tile, lat, lng, map_x, map_y, confidence, score, timestamp}
        states_seq = []
        for entry in entries:
            step_states = []

            # 1. Add valid candidates if they exist
            candidates = entry.get("candidates", [])
            for cand in candidates:
                    step_states.append({
                        "tile": cand["tile"],
                        "lat": cand["lat"],
                        "lng": cand["lng"],
                        "map_x": cand.get("map_x"),
                        "map_y": cand.get("map_y"),
                        "confidence": cand["confidence"],
                        "score": cand["score"],
                        "timestamp": entry["timestamp"],
                        "event_type": entry.get("event_type", "normal"),
                        "map_name": entry.get("map_name"),
                    })

            # 2. Add dummy lost state
            step_states.append({
                "tile": None,
                "lat": None,
                "lng": None,
                "map_x": None,
                "map_y": None,
                "confidence": 0.0,
                "score": 0,
                "timestamp": entry["timestamp"],
                "event_type": "lost",
            })

            states_seq.append(step_states)

        # Step 2: Viterbi Forward Pass
        # backpointers[t][j] = index of state at t-1 leading to state j at t
        N = len(entries)
        backpointers = []

        # Initialize t = 0
        prev_dp = []
        for state in states_seq[0]:
            if state["tile"] is None:
                prev_dp.append(self.lost_emission_cost)
            else:
                prev_dp.append(1.0 - state["confidence"])
        backpointers.append([-1] * len(states_seq[0]))

        # Forward DP loop
        for t in range(1, N):
            prev_states = states_seq[t - 1]
            curr_states = states_seq[t]

            curr_dp = []
            curr_bp = []

            for j, curr_s in enumerate(curr_states):
                # Emission cost
                if curr_s["tile"] is None:
                    emission = self.lost_emission_cost
                else:
                    emission = 1.0 - curr_s["confidence"]

                # Find min transition + prev cost
                min_cost = float("inf")
                best_i = 0
                for i, prev_s in enumerate(prev_states):
                    t_cost = self._calc_transition_cost(prev_s, curr_s)
                    cost = prev_dp[i] + t_cost
                    if cost < min_cost:
                        min_cost = cost
                        best_i = i

                curr_dp.append(min_cost + emission)
                curr_bp.append(best_i)

            prev_dp = curr_dp
            backpointers.append(curr_bp)

        # Step 3: Backtracking
        best_path_indices = []
        # Find index of best state at final frame
        min_final_cost = float("inf")
        best_final_j = 0
        for j, val in enumerate(prev_dp):
            if val < min_final_cost:
                min_final_cost = val
                best_final_j = j

        curr_j = best_final_j
        for t in range(N - 1, -1, -1):
            best_path_indices.append(curr_j)
            curr_j = backpointers[t][curr_j]

        best_path_indices.reverse()

        # Step 4: Construct optimized entries list
        optimized_entries = []
        current_segment_id = 0
        last_valid_pos = None
        was_lost = True  # Start as True so first valid position doesn't trigger teleport

        for t, idx in enumerate(best_path_indices):
            entry = entries[t].copy()
            chosen_state = states_seq[t][idx]

            tile = chosen_state["tile"]
            event_type = "normal"
            tracking_mode = "tracking"

            if tile is not None:
                # Preserve map_name from the original entry if present
                if "map_name" in entry:
                    pass
                else:
                    entry["map_name"] = chosen_state.get("map_name") or entry.get("map_name")
                if last_valid_pos is not None and not was_lost:
                    dx = chosen_state["map_x"] - last_valid_pos[0]
                    dy = chosen_state["map_y"] - last_valid_pos[1]
                    if (dx**2 + dy**2)**0.5 > TELEPORT_DISTANCE_PX:
                        current_segment_id += 1
                        event_type = "teleport"
                        tracking_mode = "relocalized"
                
                last_valid_pos = (chosen_state["map_x"], chosen_state["map_y"])
                was_lost = False
                
                entry["tile_x"] = tile[0]
                entry["tile_y"] = tile[1]
                entry["confidence"] = chosen_state["confidence"]
                entry["match_score"] = chosen_state["score"]
                entry["lat"] = chosen_state["lat"]
                entry["lng"] = chosen_state["lng"]
                entry["map_x"] = chosen_state.get("map_x")
                entry["map_y"] = chosen_state.get("map_y")
                entry["tracking_mode"] = tracking_mode
                entry["event_type"] = event_type
                entry["segment_id"] = current_segment_id
                entry["map_name"] = chosen_state.get("map_name") or entry.get("map_name")
            else:
                entry["tile_x"] = None
                entry["tile_y"] = None
                entry["confidence"] = 0.0
                entry["match_score"] = 0
                entry["lat"] = None
                entry["lng"] = None
                entry["map_x"] = None
                entry["map_y"] = None
                entry["tracking_mode"] = "lost"
                entry["event_type"] = "lost"
                entry["segment_id"] = current_segment_id
                entry["map_name"] = entry.get("map_name")
                was_lost = True

            optimized_entries.append(entry)

        # Save to optimized_route.json
        optimized_path = route_dir / "optimized_route.json"
        with open(optimized_path, "w", encoding="utf-8") as f:
            json.dump(optimized_entries, f, indent=2)

        elapsed = time.perf_counter() - start_time
        logger.info(
            f"Successfully optimized route trajectory in {elapsed:.2f} seconds. "
            f"Saved to optimized_route.json"
        )
        return optimized_path
