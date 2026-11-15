import { ActionIcon, Autocomplete, Loader } from "@mantine/core";
import { useHotkeys } from "@mantine/hooks";
import { IconSearch, IconX } from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import { searchClient } from "../lib/searchClient.js";

const SUGGEST_DELAY = 150;

/**
 * Search input with search-as-you-type suggestions (from the index vocabulary),
 * "/" to focus, and Escape to clear.
 */
export function SearchBox({ value, onChange, onSearch, loading = false, size = "md", autoFocus = false }) {
  const inputRef = useRef(null);
  const [suggestions, setSuggestions] = useState([]);
  const typedRef = useRef(false);
  const seqRef = useRef(0);

  useHotkeys([["/", () => inputRef.current?.focus()]]);

  useEffect(() => {
    if (!typedRef.current) return undefined;
    const query = value;
    const seq = ++seqRef.current;
    if (query.trim().length < 2) {
      setSuggestions([]);
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchClient
        .suggest(query, controller.signal)
        .then((list) => {
          if (seq === seqRef.current) setSuggestions((list || []).filter((s) => s.toLowerCase() !== query.toLowerCase()));
        })
        .catch(() => {});
    }, SUGGEST_DELAY);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value]);

  const submit = (query) => {
    typedRef.current = false;
    seqRef.current++;
    setSuggestions([]);
    onSearch(query);
  };

  const clear = () => {
    typedRef.current = false;
    setSuggestions([]);
    onChange("");
    inputRef.current?.focus();
  };

  const right = loading ? (
    <Loader size={18} />
  ) : value ? (
    <ActionIcon variant="subtle" color="gray" radius="xl" onClick={clear} aria-label="Clear search">
      <IconX size={18} />
    </ActionIcon>
  ) : (
    <span className="kbd-hint" aria-hidden>/</span>
  );

  return (
    <form
      role="search"
      className="searchbox"
      onSubmit={(e) => {
        e.preventDefault();
        submit(value);
      }}
    >
      <Autocomplete
        ref={inputRef}
        value={value}
        onChange={(v) => {
          typedRef.current = true;
          onChange(v);
        }}
        onOptionSubmit={submit}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !suggestions.length && value) clear();
        }}
        data={suggestions}
        filter={({ options }) => options}
        limit={8}
        placeholder="Search the index…"
        aria-label="Search"
        autoFocus={autoFocus}
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="search"
        type="search"
        size={size}
        radius="xl"
        leftSection={<IconSearch size={size === "lg" ? 22 : 18} color="var(--clea-accent)" aria-hidden />}
        leftSectionWidth={size === "lg" ? 52 : 42}
        rightSection={right}
        rightSectionWidth={44}
        rightSectionPointerEvents="all"
        comboboxProps={{ shadow: "md", transitionProps: { transition: "fade", duration: 80 } }}
      />
    </form>
  );
}
