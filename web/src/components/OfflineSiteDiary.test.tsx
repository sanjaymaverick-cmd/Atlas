import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { queueSiteDiary } from "../offline/diaryQueue";
import { OfflineSiteDiary } from "./OfflineSiteDiary";

vi.mock("../api/client", () => {
  class ApiError extends Error {
    code = "synthetic_error";
    status = 409;
  }
  return { ApiError, request: vi.fn() };
});

vi.mock("../offline/diaryQueue", () => ({
  listQueuedDiaries: vi.fn(async () => []),
  queueSiteDiary: vi.fn(async () => "synthetic-queue-id"),
  syncQueuedDiaries: vi.fn(async () => ({ submitted: 0, retained: 0 })),
}));

const mockedQueue = vi.mocked(queueSiteDiary);

afterEach(() => {
  cleanup();
  mockedQueue.mockClear();
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

describe("OfflineSiteDiary", () => {
  it("captures a privacy-minimized diary into the encrypted queue while offline", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    const user = userEvent.setup();
    render(<OfflineSiteDiary projectId="22222222-2222-2222-2222-222222222222" />);

    await user.type(screen.getByLabelText("Entry date"), "2026-08-24");
    await user.clear(screen.getByLabelText(/^Visitor count/));
    await user.type(screen.getByLabelText(/^Visitor count/), "2");
    await user.type(screen.getByLabelText("Site instructions"), "Synthetic instruction");
    await user.click(screen.getByRole("button", { name: "Save securely and queue" }));

    await waitFor(() => expect(mockedQueue).toHaveBeenCalledTimes(1));
    expect(mockedQueue).toHaveBeenCalledWith(
      "22222222-2222-2222-2222-222222222222",
      expect.objectContaining({
        entry_date: "2026-08-24",
        visitor_count: 2,
        site_instructions: "Synthetic instruction",
        labour_strength: {},
        materials_received: [],
        materials_consumed: [],
      }),
    );
    const queued = mockedQueue.mock.calls[0]?.[1];
    expect(queued?.client_record_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(queued).not.toHaveProperty("visitor_names");
    expect(await screen.findByText(/Offline: diary encrypted locally/)).toBeTruthy();
  });

  it("queues structured labour and material movements", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    const user = userEvent.setup();
    render(<OfflineSiteDiary projectId="22222222-2222-2222-2222-222222222222" />);

    await user.type(screen.getByLabelText("Entry date"), "2026-08-24");
    await user.click(screen.getByRole("button", { name: "Add trade" }));
    await user.type(screen.getByLabelText("Trade"), "Synthetic masonry");
    await user.type(screen.getByLabelText("Count"), "8");
    await user.click(screen.getAllByRole("button", { name: "Add material" })[0]!);
    await user.type(screen.getByLabelText("Material ID"), "synthetic-material-001");
    await user.type(screen.getByLabelText("Quantity"), "12.5");
    await user.type(screen.getByLabelText("Unit"), "bags");
    await user.type(screen.getByLabelText("Equipment breakdowns"), "Synthetic mixer unavailable");
    await user.click(screen.getByRole("button", { name: "Save securely and queue" }));

    await waitFor(() => expect(mockedQueue).toHaveBeenCalledTimes(1));
    expect(mockedQueue.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        labour_strength: { "Synthetic masonry": 8 },
        materials_received: [
          { material_id: "synthetic-material-001", quantity: 12.5, unit: "bags" },
        ],
        materials_consumed: [],
        equipment_breakdowns: "Synthetic mixer unavailable",
      }),
    );
  });
});
