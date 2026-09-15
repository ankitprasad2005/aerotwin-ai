import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { shouldRetryQuery } from "./api/client";
import "./index.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: shouldRetryQuery } } });

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("root element not found");

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
