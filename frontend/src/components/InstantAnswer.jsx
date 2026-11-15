import { ActionIcon, CopyButton, Group, Text, Tooltip } from "@mantine/core";
import { IconCalculator, IconCheck, IconCopy, IconRulerMeasure } from "@tabler/icons-react";

export function InstantAnswer({ answer }) {
  const isConversion = answer.type === "conversion";
  const Icon = isConversion ? IconRulerMeasure : IconCalculator;
  return (
    <section className="glass answer" aria-live="polite">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <div style={{ minWidth: 0 }}>
          <Group gap={6} mb={4}>
            <Icon size={16} color="var(--clea-accent)" aria-hidden />
            <Text size="xs" fw={600} c="var(--clea-accent)" tt="uppercase" lts={0.6}>
              {isConversion ? `${answer.dimension} conversion` : "Calculator"}
            </Text>
          </Group>
          <div className="answer-expression">{answer.expression} =</div>
          <div className="answer-value">{answer.result}</div>
        </div>
        <CopyButton value={isConversion ? answer.result : String(answer.value)}>
          {({ copied, copy }) => (
            <Tooltip label={copied ? "Copied" : "Copy result"} withArrow>
              <ActionIcon variant="subtle" color={copied ? "teal" : "gray"} onClick={copy} aria-label="Copy result">
                {copied ? <IconCheck size={18} /> : <IconCopy size={18} />}
              </ActionIcon>
            </Tooltip>
          )}
        </CopyButton>
      </Group>
    </section>
  );
}
