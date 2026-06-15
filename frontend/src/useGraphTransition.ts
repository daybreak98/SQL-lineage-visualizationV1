import { useCallback, useEffect, useRef, useState } from 'react';
import type { GraphLike, GraphTransitionPhase, PositionMap } from './types/lineage';
import {
  createGraphTransitionPlan,
  createImmediateGraphFrame,
  easeOutCubic,
  graphPositions,
  interpolatePositions,
  type GraphTransitionPlan,
} from './graphTransition';

export interface UseGraphTransitionOptions {
  previousGraph: GraphLike;
  nextGraph: GraphLike;
  enabled: boolean;
  durationMs?: number;
  onFinish?: () => void;
}

export interface GraphTransitionFrame {
  graph: GraphLike;
  positions: PositionMap;
  progress: number;
  phase: GraphTransitionPhase;
  enteringEntityIds: Set<string>;
  exitingEntityIds: Set<string>;
  cancel: () => void;
}

interface TransitionFrameState {
  graph: GraphLike;
  positions: PositionMap;
  progress: number;
  phase: GraphTransitionPhase;
  enteringEntityIds: Set<string>;
  exitingEntityIds: Set<string>;
}

export function useGraphTransition(
  options: UseGraphTransitionOptions,
): GraphTransitionFrame {
  const {
    previousGraph,
    nextGraph,
    enabled,
    durationMs = 260,
    onFinish,
  } = options;

  const rafRef = useRef<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const planRef = useRef<GraphTransitionPlan | null>(null);
  const transitionTokenRef = useRef(0);
  const onFinishRef = useRef(onFinish);

  const [frame, setFrame] = useState<TransitionFrameState>(() => ({
    graph: nextGraph,
    positions: graphPositions(nextGraph),
    progress: 1,
    phase: 'idle' as GraphTransitionPhase,
    enteringEntityIds: new Set<string>(),
    exitingEntityIds: new Set<string>(),
  }));

  onFinishRef.current = onFinish;

  const cancel = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    startedAtRef.current = null;
    planRef.current = null;
  }, []);

  useEffect(() => {
    cancel();

    if (!enabled) {
      setFrame({
        graph: nextGraph,
        positions: graphPositions(nextGraph),
        progress: 1,
        phase: 'idle',
        enteringEntityIds: new Set(),
        exitingEntityIds: new Set(),
      });
      return;
    }

    const token = ++transitionTokenRef.current;

    let plan: GraphTransitionPlan;
    try {
      plan = createGraphTransitionPlan({
        previousGraph,
        nextGraph,
        durationMs,
      });
    } catch (error) {
      console.warn('Graph transition fallback', error);
      const immediateFrame = createImmediateGraphFrame(nextGraph);
      setFrame({
        ...immediateFrame,
        phase: 'idle',
      });
      return;
    }

    planRef.current = plan;
    startedAtRef.current = performance.now();

    const tick = (now: number) => {
      if (token !== transitionTokenRef.current) {
        return;
      }

      const activePlan = planRef.current;
      const startedAt = startedAtRef.current;

      if (!activePlan || startedAt === null) {
        return;
      }

      const rawProgress = Math.min(
        1,
        (now - startedAt) / activePlan.durationMs,
      );
      const easedProgress = easeOutCubic(rawProgress);

      const positions = interpolatePositions(
        activePlan.fromPositions,
        activePlan.toPositions,
        easedProgress,
      );

      setFrame({
        graph: activePlan.renderGraph,
        positions,
        progress: rawProgress,
        phase: rawProgress < 1 ? 'running' : 'finishing',
        enteringEntityIds: activePlan.enteringEntityIds,
        exitingEntityIds: activePlan.exitingEntityIds,
      });

      if (rawProgress < 1) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }

      setFrame({
        graph: activePlan.nextGraph,
        positions: activePlan.toPositions,
        progress: 1,
        phase: 'idle',
        enteringEntityIds: new Set(),
        exitingEntityIds: new Set(),
      });

      rafRef.current = null;
      startedAtRef.current = null;
      planRef.current = null;
      onFinishRef.current?.();
    };

    rafRef.current = requestAnimationFrame(tick);

    return cancel;
  }, [previousGraph, nextGraph, enabled, durationMs, cancel]);

  return {
    ...frame,
    cancel,
  };
}
