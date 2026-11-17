import { Component, type ErrorInfo, type ReactNode } from "react";
import { t } from "../i18n";

interface Props { children: ReactNode; resetKey?: string }
interface State { error: Error | null }

/** One page breaking must not take the whole console down with it. The
 *  boundary resets when the route changes, so the next page gets a clean start. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("console page crashed", error, info.componentStack);
  }

  componentDidUpdate(prev: Props): void {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="empty crash" role="alert">
        <h2>{t("Something broke")}</h2>
        <p>{t("This page could not be drawn. The rest of the console is fine. Open another page or try again.")}</p>
        <p className="muted mono small">{error.message}</p>
        <div className="row">
          <button className="btn btn-primary" onClick={() => this.setState({ error: null })}>{t("Try again")}</button>
          <a className="btn btn-ghost" href="/dashboard">{t("Back to today")}</a>
        </div>
      </div>
    );
  }
}
