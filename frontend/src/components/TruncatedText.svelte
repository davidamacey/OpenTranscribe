<script>
  export let text = "";
  export let maxLength = 150;
  export let showMoreText = "See more";
  export let showLessText = "See less";
  
  let expanded = false;
  
  $: needsTruncation = text.length > maxLength;
  $: displayText = needsTruncation && !expanded 
    ? text.substring(0, maxLength).trim() + '...' 
    : text;

  function toggleExpanded() {
    expanded = !expanded;
  }
</script>

<div class="truncated-text">
  <p>{displayText}</p>
  {#if needsTruncation}
    <button 
      type="button" 
      class="toggle-truncation" 
      on:click={toggleExpanded}
      title={expanded ? "Show less text" : "Show the full text content"}
    >
      {expanded ? showLessText : showMoreText}
    </button>
  {/if}
</div>

<style>
  .truncated-text {
    position: relative;
    width: 100%;
  }
  
  .truncated-text p {
    margin: 0 0 0.25rem 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    line-height: 1.5;
  }
  
  .toggle-truncation {
    background: none;
    border: none;
    color: var(--primary-color);
    padding: 0;
    margin: 0;
    font-size: 0.85rem;
    cursor: pointer;
    text-decoration: underline;
    font-weight: 500;
  }
  
  .toggle-truncation:hover {
    color: var(--primary-color-dark);
  }
</style>
