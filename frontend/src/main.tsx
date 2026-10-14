import { render } from "preact";
import { App } from "./App";
import "./styles/app.css";

const rootElement = document.getElementById("app");
if (!rootElement) {
  throw new Error("Elemento raiz #app não encontrado no DOM.");
}

render(<App />, rootElement);
