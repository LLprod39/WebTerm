import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { StudioEdge } from "./StudioEdge";

vi.mock("@xyflow/react", () => ({
  BaseEdge: () => null,
  EdgeLabelRenderer: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  getBezierPath: () => ["M0 0", 100, 50],
  MarkerType: { ArrowClosed: "arrowclosed" },
}));

describe("StudioEdge", () => {
  it("passes client coordinates to onInsert", () => {
    const onInsert = vi.fn();
    render(
      <StudioEdge
        id="edge_1"
        sourceX={0}
        sourceY={0}
        targetX={200}
        targetY={0}
        sourcePosition={"right" as never}
        targetPosition={"left" as never}
        markerEnd={undefined}
        data={{ onInsert }}
        selected
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Insert node/i }), {
      clientX: 420,
      clientY: 310,
    });
    expect(onInsert).toHaveBeenCalledWith("edge_1", { x: 420, y: 310 });
  });
});
