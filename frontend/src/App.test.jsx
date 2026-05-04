import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import App from "./App";

const createFile = (name, type, size = 1024) =>
    new File(["x".repeat(size)], name, { type });

describe("File Upload Component", () => {
    test("displays error if non-PDF/DOCX/PPTX file is selected", () => {
        render(<App />);
        const input = screen.getByTestId("file-upload");
        const file = createFile("test.txt", "text/plain");

        fireEvent.change(input, { target: { files: [file] } });
        expect(screen.getByText(/pdf, txt, docx files only/i)).toBeInTheDocument();
    });

    test("displays error if file exceeds max size", () => {
        render(<App />);
        const input = screen.getByTestId("file-upload");
        // this line creates a fake file object
        const file = createFile("big.pdf", "application/pdf", 60 * 1024 * 1024);

        fireEvent.change(input, { target: { files: [file] } });
        expect(screen.getByText(/file size exceeds/i)).toBeInTheDocument(); 
    });


    test("shows upload successful message on success", async () => {
        global.fetch = jest
            .fn()
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    url: "http://fake-upload-url",
                    newFileName: "uploaded.pdf",
                }),
            })
            .mockResolvedValueOnce({ ok: true });

        render(<App />);
        const input = screen.getByTestId("file-upload");
        const file = createFile("course.pdf", "application/pdf");

        fireEvent.change(input, { target: { files: [file] } });

        const submitButton = screen.getAllByText(/^Submit$/i)[0];
        fireEvent.click(submitButton);

        await waitFor(() => {
            expect(screen.getByText(/Upload successful/i)).toBeInTheDocument();
        });
    });

    test("shows error if backend request fails", async () => {
        global.fetch = jest.fn().mockResolvedValueOnce({ ok: false });

        render(<App />);
        const input = screen.getByTestId("file-upload");
        const file = createFile("bad.pdf", "application/pdf");

        fireEvent.change(input, { target: { files: [file] } });

        const submitButton = screen.getAllByText(/^Submit$/i)[0];
        fireEvent.click(submitButton);

        await waitFor(() => {
            expect(screen.getByText(/Error:/i)).toBeInTheDocument();
        });
    });
});