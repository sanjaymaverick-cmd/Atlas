import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { request } from "../api/client";
import { TemplateBuilder } from "./TemplateBuilder";

vi.mock("../api/client", async () => {
  class ApiError extends Error {
    code = "synthetic_error";
  }
  return { ApiError, request: vi.fn() };
});

const mockedRequest = vi.mocked(request);

afterEach(() => {
  cleanup();
  mockedRequest.mockReset();
});

describe("TemplateBuilder", () => {
  it("loads a draft and submits a version-aware dynamic checklist update", async () => {
    mockedRequest.mockImplementation(async (path, options) => {
      if (path.includes("inspection-template-drafts")) {
        return [
          {
            id: "11111111-1111-1111-1111-111111111111",
            project_id: "22222222-2222-2222-2222-222222222222",
            work_package: "synthetic",
            template_name: "Synthetic Draft",
            checklist: [{ item: "Initial check", requires_evidence: false }],
            status: "draft",
            version: 3,
          },
        ] as never;
      }
      if (options?.method === "PUT") return { id: "synthetic-updated" } as never;
      throw new Error(`unexpected request ${path}`);
    });
    const user = userEvent.setup();
    render(<TemplateBuilder projectId="22222222-2222-2222-2222-222222222222" />);

    await screen.findByText("Synthetic Draft");
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Item 1"));
    await user.type(screen.getByLabelText("Item 1"), "Updated first check");
    await user.click(screen.getByRole("button", { name: "Add item" }));
    await user.type(screen.getByLabelText("Item 2"), "Second check");
    await user.click(screen.getAllByLabelText("Evidence required")[1]!);
    await user.click(screen.getByRole("button", { name: "Update draft" }));

    await waitFor(() =>
      expect(mockedRequest).toHaveBeenCalledWith(
        "/api/v1/inspection-templates/11111111-1111-1111-1111-111111111111",
        {
          method: "PUT",
          body: {
            work_package: "synthetic",
            template_name: "Synthetic Draft",
            checklist: [
              { item: "Updated first check", requires_evidence: false },
              { item: "Second check", requires_evidence: true },
            ],
            expected_version: 3,
          },
        },
      ),
    );
  });
});
