import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { HiddenLoginTrigger } from "./HiddenLoginTrigger";

const setup = () => render(
  <MemoryRouter><Routes><Route path="/" element={<HiddenLoginTrigger />} /><Route path="/platform/login" element={<p>login page</p>} /></Routes></MemoryRouter>);

test("five rapid clicks navigate to the platform login", () => {
  setup();
  const el = screen.getByTestId("hidden-login-trigger");
  for (let i = 0; i < 5; i++) fireEvent.click(el);
  expect(screen.getByText("login page")).toBeInTheDocument();
});
test("four clicks do not navigate", () => {
  setup();
  const el = screen.getByTestId("hidden-login-trigger");
  for (let i = 0; i < 4; i++) fireEvent.click(el);
  expect(screen.queryByText("login page")).toBeNull();
});
test("clicks spread beyond the time window do not navigate", () => {
  vi.useFakeTimers(); setup();
  const el = screen.getByTestId("hidden-login-trigger");
  for (let i = 0; i < 5; i++) { fireEvent.click(el); vi.advanceTimersByTime(1500); }
  expect(screen.queryByText("login page")).toBeNull(); vi.useRealTimers();
});
