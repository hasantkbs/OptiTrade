import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import styles from './ExplanationPanel.module.css'

interface ExplanationPanelProps {
  explanation: string
}

/**
 * Backed entirely by POST /quant/analyze's `explanation` field
 * (pipeline/models.py::PipelineResponse.explanation) - the Explanation
 * Engine's plain-language text. Deliberately just displayed, never fed
 * back into any calculation or used as a decision signal (WEB STEP 4
 * §10) - the note below makes that separation explicit to the reader.
 * No chat, streaming, conversation history, or direct LLM call exists
 * here or anywhere in this app.
 */
export function ExplanationPanel({ explanation }: ExplanationPanelProps) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>AI explanation</CardTitle>
          <CardSubtitle>Plain-language summary of the decision above</CardSubtitle>
        </div>
      </CardHeader>
      <p className={styles.text}>{explanation}</p>
      <p className={styles.disclaimer}>
        This explanation describes the quant decision above - it does not itself determine or adjust that decision.
      </p>
    </Card>
  )
}
