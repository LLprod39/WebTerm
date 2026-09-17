import "@testing-library/jest-dom";
import { cleanup } from "@testing-library/react";
import { createElement, type HTMLAttributes, type PropsWithChildren } from "react";
import { afterEach, vi } from "vitest";

interface MotionDivProps extends PropsWithChildren<HTMLAttributes<HTMLDivElement>> {
  animate?: unknown;
  exit?: unknown;
  initial?: unknown;
  layout?: unknown;
  layoutId?: unknown;
  transition?: unknown;
  whileHover?: unknown;
  whileTap?: unknown;
}

function motionElement(tag: "button" | "div" | "p" | "span") {
  return ({
    animate: _animate,
    children,
    exit: _exit,
    initial: _initial,
    layout: _layout,
    layoutId: _layoutId,
    transition: _transition,
    whileHover: _whileHover,
    whileTap: _whileTap,
    ...props
  }: MotionDivProps) => createElement(tag, props, children);
}

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: PropsWithChildren) => children,
  useReducedMotion: () => true,
  motion: {
    button: motionElement("button"),
    div: motionElement("div"),
    p: motionElement("p"),
    span: motionElement("span"),
  },
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
});

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, "ResizeObserver", {
  writable: true,
  value: ResizeObserverMock,
});

Object.defineProperty(Element.prototype, "scrollIntoView", {
  writable: true,
  value: () => {},
});

Object.defineProperty(window, "PointerEvent", {
  writable: true,
  value: MouseEvent,
});

Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", {
  writable: true,
  value: () => false,
});

Object.defineProperty(HTMLElement.prototype, "setPointerCapture", {
  writable: true,
  value: () => {},
});

Object.defineProperty(HTMLElement.prototype, "releasePointerCapture", {
  writable: true,
  value: () => {},
});
