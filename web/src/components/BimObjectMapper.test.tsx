import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { request } from "../api/client";
import { BimObjectMapper } from "./BimObjectMapper";

vi.mock("../api/client", async () => {
  class ApiError extends Error {
    code = "synthetic_error";
  }
  return { ApiError, request: vi.fn(async () => ({ status: "imported" })) };
});

const mockedRequest = vi.mocked(request);

afterEach(() => {
  cleanup();
  mockedRequest.mockClear();
});

describe("BimObjectMapper", () => {
  it("submits structured mappings without raw file or URL fields", async () => {
    const user = userEvent.setup();
    render(<BimObjectMapper projectId="22222222-2222-2222-2222-222222222222" />);

    await user.type(
      screen.getByLabelText("Validated BIM import ID"),
      "11111111-1111-1111-1111-111111111111",
    );
    await user.type(screen.getByLabelText("IFC GUID"), "SYNTHETIC-IFC-GUID");
    await user.selectOptions(screen.getByLabelText("Object type"), "material");
    await user.type(screen.getByLabelText("Material ID"), "33333333-3333-3333-3333-333333333333");
    await user.type(screen.getByLabelText("Room reference"), "Synthetic room");
    await user.click(screen.getByRole("button", { name: "Import structured mappings" }));

    await waitFor(() => expect(mockedRequest).toHaveBeenCalledTimes(1));
    expect(mockedRequest).toHaveBeenCalledWith(
      "/api/v1/bim-imports/11111111-1111-1111-1111-111111111111/objects",
      {
        method: "POST",
        body: {
          objects: [
            {
              ifc_guid: "SYNTHETIC-IFC-GUID",
              object_type: "material",
              material_id: "33333333-3333-3333-3333-333333333333",
              room_reference: "Synthetic room",
            },
          ],
        },
      },
    );
    const body = mockedRequest.mock.calls[0]?.[1]?.body;
    expect(body).not.toHaveProperty("file");
    expect(body).not.toHaveProperty("url");
  });
});
