import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { SessionProvider } from "@/app/session";
import { ThemeProvider } from "@/app/theme";
import { ApiError } from "@/api/client";
import { router } from "@/app/router";
import "@/styles/tokens.css";
const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, error) =>
        count < 1 &&
        !(
          error instanceof ApiError &&
          [400, 401, 403, 404, 409, 422, 429].includes(error.status)
        ),
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <SessionProvider>
          <RouterProvider router={router} />
        </SessionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
