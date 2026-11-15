import { Code, Table, Text } from "@mantine/core";

const TIPS = [
  ['"exact phrase"', "Pages containing the exact phrase"],
  ["-word", "Leave out pages containing word"],
  ["word*", "Words starting with word"],
  ["site:example.com", "Only results from that site"],
  ["intitle:word", "Word must be in the page title"],
  ["12 * (3 + 4)", "Calculator"],
  ["10 km in miles", "Unit conversion"],
];

export function SearchTips() {
  return (
    <div className="tips">
      <Table verticalSpacing={6} horizontalSpacing="sm">
        <Table.Tbody>
          {TIPS.map(([syntax, meaning]) => (
            <Table.Tr key={syntax}>
              <Table.Td style={{ whiteSpace: "nowrap" }}>
                <Code>{syntax}</Code>
              </Table.Td>
              <Table.Td>
                <Text size="sm">{meaning}</Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Text size="xs" c="dimmed" mt="xs">
        Press <Code>/</Code> anywhere to jump to the search box.
      </Text>
    </div>
  );
}
